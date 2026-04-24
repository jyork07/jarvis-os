"""
Memory Sync Script
Automatically synchronizes memories between JARVIS, OpenClaw, and Obsidian
"""

import requests
import json
import time
from datetime import datetime

# Configuration
JARVIS_API_URL = "http://127.0.0.1:7474"
JARVIS_API_TOKEN = "jarvis-openclaw-secret-2026"
OBSIDIAN_PATH = "C:\\Users\\jamie\\Documents\\JARVIS-Brain"

class MemorySync:
    """Handle memory synchronization between systems"""
    
    def __init__(self):
        self.jarvis_url = JARVIS_API_URL
        self.api_token = JARVIS_API_TOKEN
        self.headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }
    
    def check_jarvis_status(self):
        """Check if JARVIS is running and Obsidian integration is enabled"""
        try:
            response = requests.get(f"{self.jarvis_url}/api/obsidian/status", timeout=5)
            if response.status_code == 200:
                data = response.json()
                return data.get("enabled", False)
        except:
            return False
        return False
    
    def sync_jarvis_history_to_obsidian(self, limit=50):
        """Sync JARVIS chat history to Obsidian"""
        try:
            # Get recent JARVIS history
            response = requests.get(f"{self.jarvis_url}/api/history?n={limit}", timeout=10)
            if response.status_code == 200:
                history = response.json()
                
                synced_count = 0
                for entry in history:
                    # Create memory entry for each significant message
                    if len(entry.get("content", "")) > 50:
                        self._create_memory_from_history(entry)
                        synced_count += 1
                
                return synced_count
        except Exception as e:
            print(f"Error syncing JARVIS history: {e}")
        return 0
    
    def _create_memory_from_history(self, entry):
        """Create Obsidian memory from JARVIS history entry"""
        try:
            role = entry.get("role", "unknown")
            content = entry.get("content", "")
            timestamp = entry.get("ts", datetime.now().isoformat())
            
            # Create appropriate memory entry
            if role == "user":
                title = f"JARVIS User Input {timestamp[:10]}"
                memory_data = {
                    "title": title,
                    "content": content,
                    "tags": ["JARVIS", "user", "input"],
                    "source": "JARVIS",
                    "category": "general"
                }
            elif role == "assistant":
                title = f"JARVIS Response {timestamp[:10]}"
                memory_data = {
                    "title": title,
                    "content": content,
                    "tags": ["JARVIS", "assistant", "response"],
                    "source": "JARVIS",
                    "category": "general"
                }
            else:
                return
            
            # Send to JARVIS API to create memory
            response = requests.post(
                f"{self.jarvis_url}/api/obsidian/memory/create",
                headers=self.headers,
                json=memory_data,
                timeout=10
            )
            
            if response.status_code == 200:
                return True
        except Exception as e:
            print(f"Error creating memory from history: {e}")
        return False
    
    def sync_openclaw_memories(self):
        """Sync OpenClaw agent memories to Obsidian"""
        try:
            # This would integrate with OpenClaw's memory system
            # For now, we'll create a summary entry
            summary_data = {
                "title": "OpenClaw Memory Sync",
                "content": f"Memory sync completed at {datetime.now().isoformat()}",
                "tags": ["OpenClaw", "sync", "automation"],
                "source": "MemorySync",
                "category": "agent"
            }
            
            response = requests.post(
                f"{self.jarvis_url}/api/obsidian/memory/create",
                headers=self.headers,
                json=summary_data,
                timeout=10
            )
            
            return response.status_code == 200
        except Exception as e:
            print(f"Error syncing OpenClaw memories: {e}")
        return False
    
    def create_cross_references(self):
        """Create cross-references between related memories"""
        try:
            # Get recent memories
            response = requests.get(
                f"{self.jarvis_url}/api/obsidian/memory/recent?limit=20",
                headers=self.headers,
                timeout=10
            )
            
            if response.status_code == 200:
                memories = response.json().get("results", [])
                
                # Create cross-references between JARVIS memories
                jarvis_memories = [m for m in memories if "JARVIS" in m.get("content", "")]
                
                for i in range(len(jarvis_memories) - 1):
                    source = jarvis_memories[i]
                    target = jarvis_memories[i + 1]
                    
                    crosslink_data = {
                        "source_file": source.get("path", ""),
                        "target_file": target.get("path", ""),
                        "reference_type": "related"
                    }
                    
                    requests.post(
                        f"{self.jarvis_url}/api/obsidian/crosslink",
                        headers=self.headers,
                        json=crosslink_data,
                        timeout=10
                    )
        except Exception as e:
            print(f"Error creating cross-references: {e}")
    
    def run_full_sync(self):
        """Run complete memory synchronization"""
        print(f"Starting memory sync at {datetime.now().isoformat()}")
        
        # Check JARVIS status
        if not self.check_jarvis_status():
            print("JARVIS not running or Obsidian integration not enabled")
            return False
        
        print("JARVIS and Obsidian integration available")
        
        # Sync JARVIS history
        synced = self.sync_jarvis_history_to_obsidian(limit=50)
        print(f"Synced {synced} JARVIS history entries to Obsidian")
        
        # Sync OpenClaw memories
        openclaw_synced = self.sync_openclaw_memories()
        print(f"OpenClaw memory sync: {'success' if openclaw_synced else 'failed'}")
        
        # Create cross-references
        self.create_cross_references()
        print("Created cross-references between memories")
        
        print(f"Memory sync completed at {datetime.now().isoformat()}")
        return True


def main():
    """Main entry point for memory sync"""
    sync = MemorySync()
    
    # Run sync
    success = sync.run_full_sync()
    
    if success:
        print("Memory synchronization completed successfully")
    else:
        print("Memory synchronization failed")


if __name__ == "__main__":
    main()
