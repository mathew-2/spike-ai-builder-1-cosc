import json
import logging
from typing import Optional
from dataclasses import dataclass

from src.agents import BaseAgent, AgentResponse, AnalyticsAgent, SEOAgent
from src.utils import llm_client

logger = logging.getLogger(__name__)


@dataclass
class QueryIntent:
    """Represents the detected intent of a query."""
    requires_analytics: bool
    requires_seo: bool
    is_cross_agent: bool
    reasoning: str


class Orchestrator:
    """
    Central orchestrator for routing queries to appropriate agents
    and aggregating responses.
    """
    
    def __init__(self):
        self.analytics_agent = AnalyticsAgent()
        self.seo_agent = SEOAgent()
        self.agents: list[BaseAgent] = [self.analytics_agent, self.seo_agent]
    
    async def process_query(
        self,
        query: str,
        property_id: Optional[str] = None,
    ) -> dict:
        """
        Process a natural language query by routing to appropriate agent(s).
        
        Args:
            query: The natural language question
            property_id: GA4 property ID (required for analytics queries)
            
        Returns:
            Combined response from all relevant agents
        """
        try:
            # Step 1: Detect intent
            intent = await self._detect_intent(query)
            logger.info(f"Detected intent: {intent}")
            
            # Step 2: Route to appropriate agent(s)
            responses: list[AgentResponse] = []
            
            if intent.requires_analytics:
                if not property_id:
                    return {
                        "success": False,
                        "error": "GA4 propertyId is required for analytics queries",
                        "intent": {
                            "requires_analytics": True,
                            "requires_seo": intent.requires_seo,
                        },
                    }
                
                analytics_response = await self.analytics_agent.process(
                    query, property_id=property_id
                )
                responses.append(analytics_response)
            
            if intent.requires_seo:
                seo_response = await self.seo_agent.process(query)
                responses.append(seo_response)
            
            # Step 3: Aggregate responses
            if not responses:
                return {
                    "success": False,
                    "error": "Could not determine appropriate agent for this query",
                    "message": "Please rephrase your question to be about web analytics (GA4) or SEO audit data.",
                }
            
            if len(responses) == 1:
                return self._format_single_response(responses[0])
            
            # Cross-agent response fusion
            return await self._fuse_responses(query, responses, intent)
            
        except Exception as e:
            logger.exception("Error in orchestrator")
            return {
                "success": False,
                "error": str(e),
            }
    
    async def _detect_intent(self, query: str) -> QueryIntent:
        """Use LLM to detect the intent and required agents."""
        system_prompt = """You are a query router for a multi-agent system with two agents:

1. ANALYTICS AGENT: Handles Google Analytics 4 (GA4) queries about:
   - Page views, users, sessions, traffic
   - Daily/weekly breakdowns and trends
   - Traffic sources, channels
   - Conversion metrics
   - Time-series analytics data

2. SEO AGENT: Handles Screaming Frog SEO audit queries about:
   - URL analysis (HTTPS, status codes)
   - Title tags, meta descriptions
   - Indexability status
   - Page content analysis
   - Technical SEO issues

Analyze the query and return ONLY valid JSON:
{
    "requires_analytics": true/false,
    "requires_seo": true/false,
    "is_cross_agent": true/false,
    "reasoning": "brief explanation"
}

Cross-agent queries combine both (e.g., "top pages by views with their title tags").
"""
        
        response = llm_client.structured_chat(system_prompt, query, temperature=0.1)
        
        try:
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                data = json.loads(response[json_start:json_end])
                return QueryIntent(
                    requires_analytics=data.get("requires_analytics", False),
                    requires_seo=data.get("requires_seo", False),
                    is_cross_agent=data.get("is_cross_agent", False),
                    reasoning=data.get("reasoning", ""),
                )
        except json.JSONDecodeError:
            pass
        
        # Fallback: use keyword detection
        query_lower = query.lower()
        
        analytics_keywords = ["page view", "session", "traffic", "user", "ga4", "analytics", "daily", "trend"]
        seo_keywords = ["url", "title tag", "meta", "https", "indexab", "seo", "screaming frog"]
        
        has_analytics = any(kw in query_lower for kw in analytics_keywords)
        has_seo = any(kw in query_lower for kw in seo_keywords)
        
        return QueryIntent(
            requires_analytics=has_analytics or (not has_seo),  # Default to analytics
            requires_seo=has_seo,
            is_cross_agent=has_analytics and has_seo,
            reasoning="Keyword-based detection",
        )
    
    def _format_single_response(self, response: AgentResponse) -> dict:
        """Format a single agent response."""
        return {
            "success": response.success,
            "message": response.message,
            "data": response.data,
            "agent": response.agent_name,
            "error": response.error,
        }
    
    async def _fuse_responses(
        self,
        query: str,
        responses: list[AgentResponse],
        intent: QueryIntent,
    ) -> dict:
        """Fuse multiple agent responses into a unified answer."""
        
        # Check if any agent failed
        errors = [r.error for r in responses if r.error]
        if errors:
            return {
                "success": False,
                "error": "; ".join(errors),
                "partial_data": {r.agent_name: r.data for r in responses if r.success},
            }
        
        # Prepare data for fusion
        analytics_data = None
        seo_data = None
        
        for response in responses:
            if response.agent_name == "analytics":
                analytics_data = response.data
            elif response.agent_name == "seo":
                seo_data = response.data
        
        # Use LLM to generate fused response
        system_prompt = """You are synthesizing results from multiple data sources.
Combine analytics data (page views, users, etc.) with SEO data (title tags, meta descriptions, etc.)
to provide a unified, insightful answer.

Guidelines:
- Match data points across sources (e.g., URLs from analytics with SEO attributes)
- Highlight interesting correlations
- If user requested JSON, return structured JSON
- Keep response clear and actionable
"""
        
        context = f"""
User Question: {query}

Analytics Data:
{json.dumps(analytics_data, indent=2) if analytics_data else "Not available"}

SEO Data:
{json.dumps(seo_data, indent=2) if seo_data else "Not available"}

Intent: {intent.reasoning}
"""
        
        fused_message = llm_client.structured_chat(system_prompt, context)
        
        return {
            "success": True,
            "message": fused_message,
            "data": {
                "analytics": analytics_data,
                "seo": seo_data,
            },
            "agents": [r.agent_name for r in responses],
            "cross_agent": True,
        }