"""
Analytics Agent for Google Analytics 4 (GA4) queries.
Tier 1 implementation.
"""
import json
import logging
from typing import Optional
from datetime import datetime, timedelta

from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    RunReportRequest,
    DateRange,
    Dimension,
    Metric,
    FilterExpression,
    Filter,
    OrderBy,
)
from google.oauth2 import service_account

from .base import BaseAgent, AgentResponse
from src.config import config
from src.utils import llm_client

logger = logging.getLogger(__name__)


# Allowlist of valid GA4 metrics and dimensions for validation
VALID_METRICS = {
    "activeUsers", "newUsers", "totalUsers", "sessions", "sessionsPerUser",
    "screenPageViews", "screenPageViewsPerSession", "screenPageViewsPerUser",
    "engagedSessions", "engagementRate", "averageSessionDuration",
    "bounceRate", "eventCount", "eventsPerSession", "conversions",
    "totalRevenue", "purchaseRevenue", "userEngagementDuration",
    "dauPerMau", "dauPerWau", "wauPerMau",
}

VALID_DIMENSIONS = {
    "date", "dateHour", "dateHourMinute", "dayOfWeek", "dayOfWeekName",
    "month", "year", "week", "hour", "minute",
    "country", "city", "region", "continent", "subContinent",
    "language", "browser", "operatingSystem", "deviceCategory",
    "platform", "mobileDeviceBranding", "mobileDeviceModel",
    "pagePath", "pageTitle", "pageLocation", "landingPage",
    "sessionSource", "sessionMedium", "sessionCampaignName",
    "sessionDefaultChannelGroup", "firstUserSource", "firstUserMedium",
    "eventName", "hostName",
}

# Metric name mappings (common names to GA4 API names)
METRIC_MAPPINGS = {
    "page views": "screenPageViews",
    "pageviews": "screenPageViews",
    "views": "screenPageViews",
    "users": "totalUsers",
    "active users": "activeUsers",
    "new users": "newUsers",
    "sessions": "sessions",
    "bounce rate": "bounceRate",
    "engagement rate": "engagementRate",
    "session duration": "averageSessionDuration",
    "avg session duration": "averageSessionDuration",
    "events": "eventCount",
    "conversions": "conversions",
    "revenue": "totalRevenue",
}

DIMENSION_MAPPINGS = {
    "date": "date",
    "day": "date",
    "page": "pagePath",
    "page path": "pagePath",
    "path": "pagePath",
    "country": "country",
    "city": "city",
    "device": "deviceCategory",
    "browser": "browser",
    "source": "sessionSource",
    "medium": "sessionMedium",
    "channel": "sessionDefaultChannelGroup",
    "traffic source": "sessionDefaultChannelGroup",
    "landing page": "landingPage",
    "event": "eventName",
    "event name": "eventName",
}


class AnalyticsAgent(BaseAgent):
    """Agent for handling Google Analytics 4 queries."""
    
    def __init__(self):
        super().__init__("analytics")
        self._client: Optional[BetaAnalyticsDataClient] = None
    
    def _get_client(self) -> BetaAnalyticsDataClient:
        """Get or create the GA4 client using credentials from file."""
        if self._client is None:
            credentials_path = config.ga4.credentials_path
            logger.info(f"Loading GA4 credentials from: {credentials_path}")
            
            credentials = service_account.Credentials.from_service_account_file(
                str(credentials_path),
                scopes=["https://www.googleapis.com/auth/analytics.readonly"],
            )
            self._client = BetaAnalyticsDataClient(credentials=credentials)
        
        return self._client
    
    def can_handle(self, query: str) -> bool:
        """Check if query is analytics-related."""
        analytics_keywords = [
            "analytics", "ga4", "traffic", "visitors", "users", "sessions",
            "page views", "pageviews", "bounce rate", "engagement",
            "conversion", "revenue", "source", "medium", "channel",
            "daily", "weekly", "monthly", "breakdown", "trend",
        ]
        query_lower = query.lower()
        return any(keyword in query_lower for keyword in analytics_keywords)
    
    async def process(self, query: str, **kwargs) -> AgentResponse:
        """Process a GA4 analytics query."""
        property_id = kwargs.get("property_id")
        
        if not property_id:
            return AgentResponse(
                success=False,
                data=None,
                message="",
                agent_name=self.name,
                error="GA4 propertyId is required for analytics queries",
            )
        
        try:
            # Step 1: Parse the query to extract reporting plan
            reporting_plan = await self._parse_query(query)
            logger.info(f"Parsed reporting plan: {reporting_plan}")
            
            # Step 2: Validate metrics and dimensions
            validated_plan = self._validate_plan(reporting_plan)
            
            # Step 3: Execute GA4 API request
            ga4_response = self._execute_query(property_id, validated_plan)
            
            # Step 4: Generate natural language response
            response_text = await self._generate_response(
                query, validated_plan, ga4_response
            )
            
            return AgentResponse(
                success=True,
                data={
                    "reporting_plan": validated_plan,
                    "raw_data": ga4_response,
                },
                message=response_text,
                agent_name=self.name,
            )
            
        except Exception as e:
            logger.exception("Error processing analytics query")
            return AgentResponse(
                success=False,
                data=None,
                message="",
                agent_name=self.name,
                error=str(e),
            )
    
    async def _parse_query(self, query: str) -> dict:
        """Use LLM to parse natural language query into GA4 reporting plan."""
        system_prompt = """You are a GA4 query parser. Extract the following from user queries:
- metrics: List of metrics to fetch (e.g., pageviews, users, sessions)
- dimensions: List of dimensions to group by (e.g., date, page path, country)
- date_range: Start and end dates or relative range (e.g., "last 14 days")
- filters: Any filters mentioned (e.g., specific page paths)
- order_by: How to sort results if mentioned

Return ONLY valid JSON in this exact format:
{
    "metrics": ["metric1", "metric2"],
    "dimensions": ["dimension1"],
    "date_range": {"type": "relative", "days": 14},
    "filters": [{"dimension": "pagePath", "value": "/pricing"}],
    "order_by": {"field": "date", "descending": false}
}

Common mappings:
- "page views", "views" -> "screenPageViews"
- "users" -> "totalUsers"
- "daily breakdown" -> dimension: "date"
- "traffic sources" -> dimension: "sessionDefaultChannelGroup"
- "last X days" -> date_range with days: X

If information is not specified, use reasonable defaults:
- Default date range: last 7 days
- Default dimensions: ["date"] for time-series queries
"""
        
        response = llm_client.structured_chat(system_prompt, query, temperature=0.1)
        
        # Extract JSON from response
        try:
            # Try to find JSON in the response
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                return json.loads(json_str)
        except json.JSONDecodeError:
            pass
        
        # Fallback to default plan
        logger.warning("Could not parse LLM response, using defaults")
        return {
            "metrics": ["screenPageViews", "totalUsers", "sessions"],
            "dimensions": ["date"],
            "date_range": {"type": "relative", "days": 7},
            "filters": [],
            "order_by": None,
        }
    
    def _validate_plan(self, plan: dict) -> dict:
        """Validate and normalize the reporting plan against allowlists."""
        validated = {
            "metrics": [],
            "dimensions": [],
            "date_range": plan.get("date_range", {"type": "relative", "days": 7}),
            "filters": [],
            "order_by": plan.get("order_by"),
        }
        
        # Validate metrics
        for metric in plan.get("metrics", []):
            metric_lower = metric.lower()
            
            # Check if it's a common name that needs mapping
            if metric_lower in METRIC_MAPPINGS:
                api_metric = METRIC_MAPPINGS[metric_lower]
            elif metric in VALID_METRICS:
                api_metric = metric
            else:
                # Try to find closest match
                api_metric = self._find_closest_metric(metric)
            
            if api_metric and api_metric not in validated["metrics"]:
                validated["metrics"].append(api_metric)
        
        # Ensure we have at least one metric
        if not validated["metrics"]:
            validated["metrics"] = ["screenPageViews"]
        
        # Validate dimensions
        for dimension in plan.get("dimensions", []):
            dim_lower = dimension.lower()
            
            if dim_lower in DIMENSION_MAPPINGS:
                api_dim = DIMENSION_MAPPINGS[dim_lower]
            elif dimension in VALID_DIMENSIONS:
                api_dim = dimension
            else:
                api_dim = self._find_closest_dimension(dimension)
            
            if api_dim and api_dim not in validated["dimensions"]:
                validated["dimensions"].append(api_dim)
        
        # Validate filters
        for filter_item in plan.get("filters", []):
            dim = filter_item.get("dimension", "")
            if dim in VALID_DIMENSIONS or dim.lower() in DIMENSION_MAPPINGS:
                validated["filters"].append(filter_item)
        
        return validated
    
    def _find_closest_metric(self, metric: str) -> Optional[str]:
        """Find closest matching valid metric."""
        metric_lower = metric.lower()
        for valid in VALID_METRICS:
            if metric_lower in valid.lower() or valid.lower() in metric_lower:
                return valid
        return None
    
    def _find_closest_dimension(self, dimension: str) -> Optional[str]:
        """Find closest matching valid dimension."""
        dim_lower = dimension.lower()
        for valid in VALID_DIMENSIONS:
            if dim_lower in valid.lower() or valid.lower() in dim_lower:
                return valid
        return None
    
    def _execute_query(self, property_id: str, plan: dict) -> dict:
        """Execute the GA4 API query."""
        client = self._get_client()
        
        # Build date range
        date_range_config = plan.get("date_range", {})
        if date_range_config.get("type") == "relative":
            days = date_range_config.get("days", 7)
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
        else:
            start_date = datetime.fromisoformat(date_range_config.get("start", ""))
            end_date = datetime.fromisoformat(date_range_config.get("end", ""))
        
        date_ranges = [
            DateRange(
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d"),
            )
        ]
        
        # Build metrics
        metrics = [Metric(name=m) for m in plan.get("metrics", [])]
        
        # Build dimensions
        dimensions = [Dimension(name=d) for d in plan.get("dimensions", [])]
        
        # Build filters if any
        dimension_filter = None
        if plan.get("filters"):
            filter_item = plan["filters"][0]  # Take first filter for simplicity
            dim_name = filter_item.get("dimension", "pagePath")
            if dim_name.lower() in DIMENSION_MAPPINGS:
                dim_name = DIMENSION_MAPPINGS[dim_name.lower()]
            
            dimension_filter = FilterExpression(
                filter=Filter(
                    field_name=dim_name,
                    string_filter=Filter.StringFilter(
                        match_type=Filter.StringFilter.MatchType.CONTAINS,
                        value=filter_item.get("value", ""),
                    ),
                )
            )
        
        # Build request
        request = RunReportRequest(
            property=f"properties/{property_id}",
            date_ranges=date_ranges,
            metrics=metrics,
            dimensions=dimensions if dimensions else None,
            dimension_filter=dimension_filter,
            limit=1000,
        )
        
        # Execute request
        response = client.run_report(request)
        
        # Parse response into structured data
        result = {
            "rows": [],
            "totals": {},
            "row_count": response.row_count,
            "metadata": {
                "metrics": plan.get("metrics", []),
                "dimensions": plan.get("dimensions", []),
                "date_range": {
                    "start": start_date.strftime("%Y-%m-%d"),
                    "end": end_date.strftime("%Y-%m-%d"),
                },
            },
        }
        
        # Extract dimension and metric headers
        dim_headers = [h.name for h in response.dimension_headers]
        metric_headers = [h.name for h in response.metric_headers]
        
        # Extract rows
        for row in response.rows:
            row_data = {}
            
            for i, dim_value in enumerate(row.dimension_values):
                row_data[dim_headers[i]] = dim_value.value
            
            for i, metric_value in enumerate(row.metric_values):
                row_data[metric_headers[i]] = metric_value.value
            
            result["rows"].append(row_data)
        
        # Extract totals if available
        if response.totals:
            for total_row in response.totals:
                for i, metric_value in enumerate(total_row.metric_values):
                    result["totals"][metric_headers[i]] = metric_value.value
        
        return result
    
    async def _generate_response(
        self, original_query: str, plan: dict, ga4_data: dict
    ) -> str:
        """Generate natural language response from GA4 data."""
        system_prompt = """You are a data analyst explaining GA4 analytics results.
Given the user's question and the GA4 data, provide a clear, insightful response.

Guidelines:
- Summarize key findings first
- Highlight trends if time-series data is present
- Mention specific numbers and percentages
- If data is empty or sparse, explain this gracefully
- Keep response concise but informative
- If the user requested JSON format, return data as JSON instead
"""
        
        context = f"""
User Question: {original_query}

Query Plan:
- Metrics: {plan.get('metrics', [])}
- Dimensions: {plan.get('dimensions', [])}
- Date Range: {plan.get('date_range', {})}
- Filters: {plan.get('filters', [])}

GA4 Results:
- Total Rows: {ga4_data.get('row_count', 0)}
- Data: {json.dumps(ga4_data.get('rows', [])[:20], indent=2)}
- Totals: {json.dumps(ga4_data.get('totals', {}), indent=2)}
"""
        
        return llm_client.structured_chat(system_prompt, context)
