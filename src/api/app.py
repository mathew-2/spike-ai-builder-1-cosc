import logging
from logging import config
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel,Field


from src.orchestrator.orchestrator import Orchestrator
from src.utils import setup_logging
from src.config import config


logger = setup_logging()

class QueryRequest(BaseModel):

    query: str = Field(..., description="Natural language question")
    propertyId: Optional[str] = Field(
        None, description="GA4 Property ID (required for analytics queries)"
    )

class QueryResponse(BaseModel):
    """Response from the /query endpoint."""
    success: bool
    message: Optional[str] = None
    data: Optional[dict] = None
    agent: Optional[str] = None
    agents: Optional[list[str]] = None
    cross_agent: Optional[bool] = None
    error: Optional[str] = None


# # Global orchestrator instance
# orchestrator: Optional[Orchestrator] = None

orchestrator = Orchestrator()
# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     """Application lifespan manager."""
#     global orchestrator
    
#     # Startup
#     logger.info("Starting Spike AI Builder...")
#     logger.info(f"Server will run on {config.server.host}:{config.server.port}")
    
#     orchestrator = Orchestrator()
#     logger.info("Orchestrator initialized with Analytics and SEO agents")
    
#     yield
    
#     # Shutdown
#     logger.info("Shutting down Spike AI Builder...")


app = FastAPI(
    title="Spike AI Builder",
    description="AI-powered backend for web analytics and SEO queries",
    version="1.0.0",
)


@app.get("/")
async def root():
    return {
        "status": "healthy",
        "service": "Spike AI Builder",
        "version": "1.0.0",
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest):

    if orchestrator is None:
        raise HTTPException(
            status_code=503,
            detail="Service not initialized",
        )
    
    logger.info(f"Received query: {request.query[:100]}...")
    if request.propertyId:
        logger.info(f"Property ID: {request.propertyId}")
    
    try:
        result = await orchestrator.process_query(
            query=request.query,
            property_id=request.propertyId,
        )
        
        return QueryResponse(**result)
        
    except Exception as e:
        logger.exception("Error processing query")
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )
