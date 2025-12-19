import json
import logging
from typing import Optional
import pandas as pd

from .base import BaseAgent, AgentResponse
from src.config import config
from src.utils import llm_client

import time
from google.oauth2 import service_account
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)


class SEOAgent(BaseAgent):
    """Agent for handling SEO audit queries from Screaming Frog data."""
    
    def __init__(self):
        super().__init__("seo")
        self._data_cache: Optional[pd.DataFrame] = None
        self._cache_timestamp: Optional[float] = None
        self._cache_ttl = 300  # 5 minutes cache
    
    def can_handle(self, query: str) -> bool:
        """Check if query is SEO-related."""
        seo_keywords = [
            "seo", "url", "urls", "title tag", "meta description",
            "https", "http", "indexable", "indexability", "crawl",
            "screaming frog", "audit", "404", "redirect", "canonical",
            "h1", "heading", "content", "word count", "duplicate",
            "robots", "sitemap", "status code",
        ]
        query_lower = query.lower()
        return any(keyword in query_lower for keyword in seo_keywords)
    
    async def process(self, query: str, **kwargs) -> AgentResponse:
        """Process an SEO-related query."""
        try:
            # Step 1: Load SEO data from Google Sheets
            df = await self._load_data()
            
            if df is None or df.empty:
                return AgentResponse(
                    success=False,
                    data=None,
                    message="",
                    agent_name=self.name,
                    error="Failed to load SEO data from spreadsheet",
                )
            
            # Step 2: Parse query to understand the analysis needed
            analysis_plan = await self._parse_query(query, df.columns.tolist())
            logger.info(f"SEO analysis plan: {analysis_plan}")
            
            # Step 3: Execute the analysis
            result_data = self._execute_analysis(df, analysis_plan)
            
            # Step 4: Generate natural language response
            response_text = await self._generate_response(
                query, analysis_plan, result_data, df.shape[0]
            )
            
            return AgentResponse(
                success=True,
                data={
                    "analysis_plan": analysis_plan,
                    "result_data": result_data,
                    "total_urls": df.shape[0],
                },
                message=response_text,
                agent_name=self.name,
            )
            
        except Exception as e:
            logger.exception("Error processing SEO query")
            return AgentResponse(
                success=False,
                data=None,
                message="",
                agent_name=self.name,
                error=str(e),
            )
    
    async def _load_data(self) -> Optional[pd.DataFrame]:
        """Load SEO data from Google Sheets."""
        import time
        
        # Check cache
        current_time = time.time()
        if (
            self._data_cache is not None
            and self._cache_timestamp
            and (current_time - self._cache_timestamp) < self._cache_ttl
        ):
            logger.debug("Using cached SEO data")
            return self._data_cache
        
        try:
            spreadsheet_id = config.seo.spreadsheet_id
            

            logger.info(f"Using SEO credentials at: {config.seo.credentials_path}")
        
            # Use service account credentials
            credentials = service_account.Credentials.from_service_account_file(
                str(config.seo.credentials_path),
                scopes=['https://www.googleapis.com/auth/spreadsheets.readonly']
            )
            
            # Build the Sheets API service
            service = build('sheets', 'v4', credentials=credentials)
            
            # Get all data from the first sheet
            result = service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range='Sheet1!A1:ZZ'  # Get all columns
            ).execute()
            
            values = result.get('values', [])

            logger.info(f"Sheets API response keys: {result.keys()}")
            logger.info(f"Rows returned from Sheets API: {len(values)}")
            
            if not values:
                logger.warning("No data found in spreadsheet")
                return None
            
            # Convert to DataFrame (first row as headers)
            headers = values[0]
            data = values[1:]

            df = pd.DataFrame(data, columns=headers)

            # Clean column names
            df.columns = df.columns.str.strip()
            
            # Cache the data
            self._data_cache = df
            self._cache_timestamp = current_time
            
            logger.info(f"Loaded {len(df)} rows with columns: {df.columns.tolist()}")
            return df
                
        except Exception as e:
            logger.error(f"Failed to load SEO data: {e}")
            return None

    async def _parse_query(self, query: str, columns: list) -> dict:
        """Use LLM to parse the SEO query into an analysis plan."""
        system_prompt = f"""You are an SEO data analyst. Parse the user's query to determine what analysis to perform.

Available columns in the data: {columns}

Common column mappings:
- URL, Address -> the page URL
- Title, Title 1 -> title tag
- Meta Description, Meta Description 1 -> meta description
- Status Code -> HTTP status
- Indexability -> whether page is indexable
- Content Type -> page content type
- Word Count -> content length

Return ONLY valid JSON in this format:
{{
    "operation": "filter|group|aggregate|count|list",
    "filters": [
        {{"column": "column_name", "operator: equals|contains|not_contains|greater|less|not_equals|is_empty|not_empty", "value": "value"}}
    ],
    "group_by": "column_name or null",
    "aggregation": "count|sum|mean|null",
    "select_columns": ["col1", "col2"],
    "limit": 100,
    "return_json": false
}}

Examples:
- "URLs without HTTPS" -> filter where URL not contains "https"
- "Group by indexability" -> group_by: "Indexability", aggregation: "count"
- "Title tags longer than 60 chars" -> filter where title length > 60
- "Return in JSON format" -> return_json: true
"""
        
        response = llm_client.structured_chat(system_prompt, query, temperature=0.1)
        
        try:
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                return json.loads(response[json_start:json_end])
        except json.JSONDecodeError:
            pass
        
        # Fallback default
        return {
            "operation": "list",
            "filters": [],
            "group_by": None,
            "aggregation": None,
            "select_columns": [],
            "limit": 100,
            "return_json": False,
        }
    
    def _execute_analysis(self, df: pd.DataFrame, plan: dict) -> dict:
        """Execute the SEO analysis based on the plan."""
        result_df = df.copy()
        
        # Apply filters
        for filter_item in plan.get("filters", []):
            column = self._find_column(df, filter_item.get("column", ""))
            if column is None:
                continue
            
            operator = filter_item.get("operator", "equals")
            value = filter_item.get("value", "")
            
            if operator == "equals":
                result_df = result_df[result_df[column] == value]
            elif operator == "not_equals":
                result_df = result_df[result_df[column] != value]
            elif operator == "contains":
                result_df = result_df[
                    result_df[column].astype(str).str.contains(value, case=False, na=False)
                ]
            elif operator == "not_contains":
                result_df = result_df[
                    ~result_df[column].astype(str).str.contains(value, case=False, na=False)
                ]
            elif operator == "greater":
                # Handle length comparisons for string columns
                if "length" in str(filter_item.get("column", "")).lower():
                    result_df = result_df[
                        result_df[column].astype(str).str.len() > float(value)
                    ]
                else:
                    result_df = result_df[
                        pd.to_numeric(result_df[column], errors="coerce") > float(value)
                    ]
            elif operator == "less":
                if "length" in str(filter_item.get("column", "")).lower():
                    result_df = result_df[
                        result_df[column].astype(str).str.len() < float(value)
                    ]
                else:
                    result_df = result_df[
                        pd.to_numeric(result_df[column], errors="coerce") < float(value)
                    ]
            elif operator == "is_empty":
                result_df = result_df[
                    result_df[column].isna() | (result_df[column].astype(str).str.strip() == "")
                ]
            elif operator == "not_empty":
                result_df = result_df[
                    result_df[column].notna() & (result_df[column].astype(str).str.strip() != "")
                ]
        
        # Handle grouping
        if plan.get("group_by"):
            group_col = self._find_column(df, plan["group_by"])
            if group_col:
                if plan.get("aggregation") == "count":
                    grouped = result_df.groupby(group_col).size().reset_index(name="count")
                    return {
                        "type": "grouped",
                        "data": grouped.to_dict(orient="records"),
                        "total_groups": len(grouped),
                    }
                elif plan.get("aggregation") == "sum":
                    grouped = result_df.groupby(group_col).sum(numeric_only=True).reset_index()
                    return {
                        "type": "grouped",
                        "data": grouped.to_dict(orient="records"),
                        "total_groups": len(grouped),
                    }
        
        # Select specific columns if requested
        select_cols = plan.get("select_columns", [])
        if select_cols:
            valid_cols = [self._find_column(df, c) for c in select_cols]
            valid_cols = [c for c in valid_cols if c is not None]
            if valid_cols:
                result_df = result_df[valid_cols]
        
        # Apply limit
        limit = plan.get("limit", 100)
        result_df = result_df.head(limit)
        
        return {
            "type": "list",
            "data": result_df.to_dict(orient="records"),
            "total_matching": len(result_df),
            "columns": result_df.columns.tolist(),
        }
    
    def _find_column(self, df: pd.DataFrame, search: str) -> Optional[str]:
        """Find the best matching column name."""
        if not search:
            return None
        
        search_lower = search.lower().strip()
        
        # Exact match first
        for col in df.columns:
            if col.lower() == search_lower:
                return col
        
        # Partial match
        for col in df.columns:
            if search_lower in col.lower() or col.lower() in search_lower:
                return col
        
        # Common mappings
        mappings = {
            "url": ["address", "url"],
            "title": ["title 1", "title", "title tag"],
            "meta description": ["meta description 1", "meta description"],
            "status": ["status code"],
            "indexability": ["indexability", "indexable"],
            "content": ["content type"],
            "word count": ["word count"],
            "h1": ["h1-1", "h1"],
        }
        
        for key, alternatives in mappings.items():
            if search_lower in key or key in search_lower:
                for alt in alternatives:
                    for col in df.columns:
                        if alt in col.lower():
                            return col
        
        return None
    
    async def _generate_response(
        self, query: str, plan: dict, result: dict, total_urls: int
    ) -> str:
        """Generate natural language response from SEO analysis."""
        
        # If JSON format was requested, return structured JSON
        if plan.get("return_json"):
            return json.dumps(result.get("data", []), indent=2)
        
        system_prompt = """You are an SEO expert explaining audit results.
Given the user's question and the analysis results, provide clear insights.

Guidelines:
- Summarize key findings first
- Provide specific counts and percentages
- Explain SEO implications when relevant
- If results are empty, explain what this means
- Keep response concise but actionable
- For indexability questions, explain what indexable/non-indexable means
"""
        
        context = f"""
User Question: {query}

Analysis:
- Operation: {plan.get('operation')}
- Filters applied: {plan.get('filters', [])}
- Group by: {plan.get('group_by')}

Results:
- Type: {result.get('type')}
- Total URLs in dataset: {total_urls}
- Matching results: {result.get('total_matching', result.get('total_groups', 0))}
- Data sample: {json.dumps(result.get('data', [])[:10], indent=2)}
"""
        
        return llm_client.structured_chat(system_prompt, context)
