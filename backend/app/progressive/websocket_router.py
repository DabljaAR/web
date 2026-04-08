"""WebSocket router for progressive video updates."""
import asyncio
import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.progressive.notifications import notifier
from app.progressive.service import ProgressiveVideoBuilder
from app.core.db import get_db

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/progressive/{job_id}")
async def progressive_updates_websocket(
    websocket: WebSocket, 
    job_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    WebSocket endpoint for real-time progressive dubbing updates.
    
    Messages sent to client:
    - segment_merged: When individual segment completes
    - video_updated: When new progressive video URL available  
    - segment_status_change: When segment status changes
    - job_completed: When entire job finishes
    - error: When errors occur
    - heartbeat: Keep-alive messages
    - initial_state: Current progress on connection
    
    TODO: Add authentication when needed
    """
    
    await websocket.accept()
    
    try:
        # Verify job exists
        builder = ProgressiveVideoBuilder(db)
        progress = await builder.get_current_progress(job_id)
        
        if "error" in progress:
            await websocket.send_text(json.dumps({
                "type": "error",
                "error_type": "job_not_found",
                "error_message": "Job not found"
            }))
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        
        # Register for job-specific updates
        await notifier.register_job_listener(job_id, websocket)
        
        # Send current progress on connection
        await websocket.send_text(json.dumps({
            "type": "initial_state",
            **progress
        }))
        
        logger.info(f"[WEBSOCKET] Connected to job {job_id}")
        
        # Keep connection alive and handle client messages
        while True:
            try:
                # Wait for client messages with timeout for periodic checks
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                message = json.loads(data)
                
                await handle_client_message(websocket, job_id, message, builder)
                
            except asyncio.TimeoutError:
                # Send periodic heartbeat
                await websocket.send_text(json.dumps({"type": "heartbeat"}))
                
            except Exception as e:
                logger.error(f"[WEBSOCKET] Error processing message | job={job_id} | error={e}")
                # Continue the loop, don't break on message processing errors
                
    except WebSocketDisconnect:
        logger.info(f"[WEBSOCKET] Disconnected from job {job_id}")
    except Exception as e:
        logger.error(f"[WEBSOCKET] Unexpected error | job={job_id} | error={e}")
    finally:
        # Always clean up the connection
        await notifier.unregister_job_listener(job_id, websocket)


async def handle_client_message(websocket: WebSocket, job_id: str, message: dict, builder: ProgressiveVideoBuilder):
    """Handle messages sent by the client."""
    
    message_type = message.get("type")
    
    try:
        if message_type == "request_current_state":
            # Client requesting current progress
            progress = await builder.get_current_progress(job_id)
            await websocket.send_text(json.dumps({
                "type": "current_state",
                **progress
            }))
            
        elif message_type == "ping":
            # Ping/pong for connection testing
            await websocket.send_text(json.dumps({
                "type": "pong",
                "timestamp": message.get("timestamp")
            }))
            
        elif message_type == "subscribe_to_events":
            # Client can specify which event types they want
            event_types = message.get("event_types", [])
            await websocket.send_text(json.dumps({
                "type": "subscription_confirmed",
                "subscribed_events": event_types
            }))
            
        else:
            # Unknown message type
            await websocket.send_text(json.dumps({
                "type": "error",
                "error_type": "unknown_message_type",
                "error_message": f"Unknown message type: {message_type}"
            }))
            
    except Exception as e:
        logger.error(f"[WEBSOCKET] Error handling client message | job={job_id} | type={message_type} | error={e}")
        await websocket.send_text(json.dumps({
            "type": "error",
            "error_type": "message_processing_error",
            "error_message": "Failed to process message"
        }))


# REST endpoints for progressive status

@router.get("/api/progressive/{job_id}/status")
async def get_progressive_status(
    job_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get current progressive status via REST API."""
    
    builder = ProgressiveVideoBuilder(db)
    progress = await builder.get_current_progress(job_id)
    
    if "error" in progress:
        raise HTTPException(
            status_code=404,
            detail=f"Progressive job {job_id} not found"
        )
    
    return progress


@router.get("/api/progressive/stats")
async def get_notifier_stats():
    """Get WebSocket notifier statistics."""
    
    stats = await notifier.get_connection_stats()
    return {
        "success": True,
        "stats": stats
    }