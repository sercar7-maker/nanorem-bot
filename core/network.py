"""Network Management Module for NANOREM MLM System

Manages the MLM network structure, partner relationships, and genealogy tree.
"""

from typing import Dict, List, Optional, Set
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


class NetworkManager:
    """Manager for MLM Network Structure and Relationships"""
    
    def __init__(self):
        self.network: Dict[int, List[int]] = {}  # partner_id -> list of downline IDs
        self.upline_map: Dict[int, Optional[int]] = {}  # partner_id -> upline_id
        self.logger = logger
    
    def add_partner(self, partner_id: int, upline_id: Optional[int] = None) -> bool:
        """Add partner to network."""
        if partner_id in self.network:
            self.logger.warning(f"Partner {partner_id} already in network")
            return False
        
        self.network[partner_id] = []
        self.upline_map[partner_id] = upline_id
        
        if upline_id is not None:
            if upline_id not in self.network:
                self.network[upline_id] = []
            self.network[upline_id].append(partner_id)
        
        self.logger.info(f"Added partner {partner_id} under {upline_id}")
        return True
    
    def get_upline_chain(self, partner_id: int, max_levels: Optional[int] = None) -> List[int]:
        """Get upline chain for partner."""
        chain = []
        current_id = self.upline_map.get(partner_id)
        level = 0
        
        while current_id is not None and (max_levels is None or level < max_levels):
            chain.append(current_id)
            current_id = self.upline_map.get(current_id)
            level += 1
        
        return chain
    
    def get_downline(self, partner_id: int, recursive: bool = False) -> List[int]:
        """Get downline partners."""
        if partner_id not in self.network:
            return []
        
        if not recursive:
            return self.network[partner_id].copy()
        
        # Recursive downline
        all_downline = []
        to_process = [partner_id]
        
        while to_process:
            current = to_process.pop(0)
            children = self.network.get(current, [])
            all_downline.extend(children)
            to_process.extend(children)
        
        return all_downline
    
    def get_network_depth(self, partner_id: int) -> int:
        """Get maximum depth of network below partner."""
        if partner_id not in self.network or not self.network[partner_id]:
            return 0
        
        max_depth = 0
        for child_id in self.network[partner_id]:
            child_depth = self.get_network_depth(child_id)
            max_depth = max(max_depth, child_depth + 1)
        
        return max_depth
    
    def get_network_size(self, partner_id: int) -> int:
        """Get total size of network below partner."""
        return len(self.get_downline(partner_id, recursive=True))
    
    def get_level_partners(self, partner_id: int, level: int) -> List[int]:
        """Get all partners at specific level below partner."""
        if level == 0:
            return [partner_id]
        if level == 1:
            return self.network.get(partner_id, [])
        
        partners_at_level = []
        current_level = self.network.get(partner_id, [])
        
        for _ in range(1, level):
            next_level = []
            for p_id in current_level:
                next_level.extend(self.network.get(p_id, []))
            current_level = next_level
        
        return current_level
    
    def get_network_tree(self, partner_id: int, max_depth: Optional[int] = None) -> Dict:
        """Get network tree structure."""
        if max_depth == 0:
            return {'partner_id': partner_id, 'children': []}
        
        children_trees = []
        for child_id in self.network.get(partner_id, []):
            next_depth = None if max_depth is None else max_depth - 1
            child_tree = self.get_network_tree(child_id, next_depth)
            children_trees.append(child_tree)
        
        return {'partner_id': partner_id, 'children': children_trees}
