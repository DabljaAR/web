"""Real-time progress notification system using WebSocket broadcasting."""
import asyncio
import json
import logging
import time
from typing import Dict, List, Set, Optional
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ProgressNotifier:
    """
    Real-time progress notification system using WebSocket broadcasting.
    """
    
    def __init__(self):
        # Active WebSocket connections per job
        self.job_connections: Dict[str, Set[WebSocket]] = {}
        # Global connections for all jobs
        self.global_connections: Set[WebSocket] = set()
        # Connection metadata (user_id, permissions, etc.)
        self.connection_metadata: Dict[WebSocket, Dict] = {}
        
    async def register_job_listener(self, job_id: str, websocket: WebSocket, user_metadata: Optional[Dict] = None):
        """Register WebSocket for specific job progress updates."""
        if job_id not in self.job_connections:
            self.job_connections[job_id] = set()
        
        self.job_connections[job_id].add(websocket)
        
        # Store connection metadata
        self.connection_metadata[websocket] = {
            "job_id": job_id,
            "connected_at": time.time(),
            **(user_metadata or {})
        }
        
        logger.info(f"[NOTIFIER] Registered listener | job={job_id} | connections={len(self.job_connections[job_id])}")
    
    async def unregister_job_listener(self, job_id: str, websocket: WebSocket):
        """Unregister WebSocket from job updates."""
        if job_id in self.job_connections:
            self.job_connections[job_id].discard(websocket)
            if not self.job_connections[job_id]:
                del self.job_connections[job_id]
        
        # Remove connection metadata
        self.connection_metadata.pop(websocket, None)
        
        logger.debug(f"[NOTIFIER] Unregistered listener | job={job_id}")
    
    async def register_global_listener(self, websocket: WebSocket, user_metadata: Optional[Dict] = None):
        """Register WebSocket for all job updates (admin/monitoring)."""
        self.global_connections.add(websocket)
        
        # Store connection metadata
        self.connection_metadata[websocket] = {
            "type": "global",
            "connected_at": time.time(),
            **(user_metadata or {})
        }
        
        logger.info(f"[NOTIFIER] Registered global listener | total={len(self.global_connections)}")
    
    async def unregister_global_listener(self, websocket: WebSocket):
        """Unregister WebSocket from global updates."""
        self.global_connections.discard(websocket)
        self.connection_metadata.pop(websocket, None)
        
        logger.debug(f"[NOTIFIER] Unregistered global listener")
    
    async def notify_segment_merged(
        self, 
        job_id: str, 
        segment_id: int, 
        completion_percentage: float,
        video_url: Optional[str] = None
    ):
        """Broadcast segment merge completion to all listeners."""
        
        message = {
            "type": "segment_merged",
            "job_id": job_id,
            "segment_id": segment_id,
            "completion_percentage": completion_percentage,
            "video_url": video_url,
            "timestamp": time.time()
        }
        
        await self._broadcast_to_job(job_id, message)
        await self._broadcast_to_global(message)
    
    async def notify_video_updated(self, job_id: str, video_url: str):
        """Notify listeners of new progressive video URL."""
        
        message = {
            "type": "video_updated", 
            "job_id": job_id,
            "video_url": video_url,
            "timestamp": time.time()
        }
        
        await self._broadcast_to_job(job_id, message)
        await self._broadcast_to_global(message)
    
    async def notify_segment_status_change(
        self,
        job_id: str,
        segment_id: int,
        old_status: str,
        new_status: str,
        error_message: Optional[str] = None
    ):
        """Notify listeners of segment status changes."""
        
        message = {
            "type": "segment_status_change",
            "job_id": job_id,
            "segment_id": segment_id,
            "old_status": old_status,
            "new_status": new_status,
            "error_message": error_message,
            "timestamp": time.time()
        }
        
        await self._broadcast_to_job(job_id, message)
    
    async def notify_job_completed(self, job_id: str, final_video_url: str, stats: Dict):
        """Notify listeners when entire job completes."""
        
        message = {
            "type": "job_completed",
            "job_id": job_id,
            "final_video_url": final_video_url,
            "stats": stats,
            "timestamp": time.time()
        }
        
        await self._broadcast_to_job(job_id, message)
        await self._broadcast_to_global(message)
    
    async def notify_error(self, job_id: str, error_type: str, error_message: str, segment_id: Optional[int] = None):
        """Notify listeners of errors."""
        
        message = {
            "type": "error",
            "job_id": job_id,
            "error_type": error_type,
            "error_message": error_message,
            "segment_id": segment_id,
            "timestamp": time.time()
        }
        
        await self._broadcast_to_job(job_id, message)
        await self._broadcast_to_global(message)
    
    async def send_heartbeat(self, job_id: Optional[str] = None):
        """Send heartbeat to keep connections alive."""
        
        message = {
            "type": "heartbeat",
            "timestamp": time.time()
        }
        
        if job_id:
            await self._broadcast_to_job(job_id, message)
        else:
            await self._broadcast_to_global(message)
    
    async def get_connection_stats(self) -> Dict:
        """Get statistics about active connections."""
        
        total_job_connections = sum(len(connections) for connections in self.job_connections.values())
        
        return {
            "active_jobs": len(self.job_connections),
            "total_job_connections": total_job_connections,
            "global_connections": len(self.global_connections),
            "total_connections": total_job_connections + len(self.global_connections),
            "jobs_with_listeners": list(self.job_connections.keys())
        }
    
    # Internal broadcast methods
    
    async def _broadcast_to_job(self, job_id: str, message: Dict):
        """Send message to all WebSocket connections for specific job."""
        
        if job_id not in self.job_connections:
            return
        
        # Create copy to avoid modification during iteration
        connections = list(self.job_connections[job_id])
        disconnected = []
        
        message_json = json.dumps(message)
        
        for websocket in connections:
            try:
                await websocket.send_text(message_json)
            except Exception as e:
                logger.warning(f"[NOTIFIER] Failed to send to WebSocket | job={job_id} | error={e}")
                disconnected.append(websocket)
        
        # Clean up disconnected sockets
        for ws in disconnected:
            await self.unregister_job_listener(job_id, ws)
    
    async def _broadcast_to_global(self, message: Dict):
        """Send message to all global WebSocket connections."""
        
        if not self.global_connections:
            return
        
        # Create copy to avoid modification during iteration
        connections = list(self.global_connections)
        disconnected = []
        
        message_json = json.dumps(message)
        
        for websocket in connections:
            try:
                await websocket.send_text(message_json)
            except Exception as e:
                logger.warning(f"[NOTIFIER] Failed to send to global WebSocket | error={e}")
                disconnected.append(websocket)
        
        # Clean up disconnected sockets
        for ws in disconnected:
            await self.unregister_global_listener(ws)
    
    async def cleanup_dead_connections(self):
        """Periodic cleanup of dead connections."""
        current_time = time.time()
        timeout = 300  # 5 minutes
        
        dead_connections = []
        
        for websocket, metadata in self.connection_metadata.items():
            if current_time - metadata.get("connected_at", 0) > timeout:
                # Check if connection is still alive
                try:
                    await websocket.ping()
                except Exception:
                    dead_connections.append(websocket)
        
        # Clean up dead connections
        for ws in dead_connections:
            metadata = self.connection_metadata.get(ws, {})
            job_id = metadata.get("job_id")
            
            if job_id:
                await self.unregister_job_listener(job_id, ws)
            else:
                await self.unregister_global_listener(ws)
            
            logger.debug(f"[NOTIFIER] Cleaned up dead connection | job={job_id}")


# Global notifier instance
notifier = ProgressNotifier()


async def start_heartbeat_task():
    """Start periodic heartbeat task."""
    async def heartbeat_loop():
        while True:
            try:
                await notifier.send_heartbeat()
                await notifier.cleanup_dead_connections()
                await asyncio.sleep(30)  # Send heartbeat every 30 seconds
            except Exception as e:
                logger.error(f"[NOTIFIER] Heartbeat task error: {e}")
                await asyncio.sleep(5)
    
    # Start the heartbeat task
    asyncio.create_task(heartbeat_loop())