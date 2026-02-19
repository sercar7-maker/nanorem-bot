"""Network Management Module for NANOREM MLM System

Manages the MLM network structure, partner relationships, and genealogy tree.

Key rules:
- Unlimited branches per partner (no width limit).
- Maximum commission depth: 5 levels (MAX_LEVELS).
- Partner activity flag (is_active) drives compression logic in commission.py.
- Structural compression (re-parenting): when a partner is deactivated,
  their direct children are re-attached to the nearest active upline partner,
  so the branch is never orphaned.
"""
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)

# Maximum levels for commission payout (mirrors commission.py)
MAX_LEVELS = 5


@dataclass
class PartnerNode:
    """Lightweight node representing a partner in the network graph."""
    partner_id: int
    upline_id: Optional[int] = None
    is_active: bool = True
    downline_ids: List[int] = field(default_factory=list)


class NetworkManager:
    """
    Manager for NANOREM MLM Network Structure and Relationships.

    Responsibilities:
    - Add / deactivate partners.
    - Maintain upline/downline maps.
    - Provide upline chain in the format expected by CommissionCalculator:
        List[Tuple[partner_id: int, is_active: bool]]
    - Structural compression on deactivation: children of an inactive partner
      are re-parented to the nearest active ancestor.
    """

    def __init__(self):
        # partner_id -> PartnerNode
        self._nodes: Dict[int, PartnerNode] = {}
        self.logger = logger

    # -----------------------------------------------------------------------
    # Partner lifecycle
    # -----------------------------------------------------------------------

    def add_partner(
        self,
        partner_id: int,
        upline_id: Optional[int] = None
    ) -> bool:
        """
        Register a new active partner in the network.

        Args:
            partner_id: Unique ID of the new partner.
            upline_id:  ID of the direct sponsor. None for root partners.

        Returns:
            True if added, False if partner already exists.
        """
        if partner_id in self._nodes:
            self.logger.warning(f"Partner {partner_id} already in network")
            return False

        # Auto-register upline node if missing (edge case / data repair)
        if upline_id is not None and upline_id not in self._nodes:
            self.logger.warning(
                f"Upline {upline_id} not found — auto-registering as root."
            )
            self._nodes[upline_id] = PartnerNode(partner_id=upline_id)

        node = PartnerNode(partner_id=partner_id, upline_id=upline_id)
        self._nodes[partner_id] = node

        if upline_id is not None:
            self._nodes[upline_id].downline_ids.append(partner_id)

        self.logger.info(f"Added partner {partner_id} under {upline_id}")
        return True

    def deactivate_partner(self, partner_id: int, compress: bool = True) -> bool:
        """
        Deactivate a partner.

        Args:
            partner_id: Partner to deactivate.
            compress:   If True, re-parent this partner's direct children
                        to the nearest active ancestor (structural compression).

        Returns:
            True if deactivated, False if partner not found.
        """
        if partner_id not in self._nodes:
            self.logger.warning(f"Partner {partner_id} not found")
            return False

        node = self._nodes[partner_id]
        node.is_active = False
        self.logger.info(f"Partner {partner_id} deactivated")

        if compress and node.downline_ids:
            self._compress_upward(partner_id)

        return True

    def reactivate_partner(self, partner_id: int) -> bool:
        """
        Reactivate a previously deactivated partner.

        Note: re-parenting after reactivation is NOT automatic;
        structural positions must be managed by the caller if needed.

        Returns:
            True if reactivated, False if partner not found.
        """
        if partner_id not in self._nodes:
            self.logger.warning(f"Partner {partner_id} not found")
            return False

        self._nodes[partner_id].is_active = True
        self.logger.info(f"Partner {partner_id} reactivated")
        return True

    # -----------------------------------------------------------------------
    # Structural compression
    # -----------------------------------------------------------------------

    def _compress_upward(self, inactive_partner_id: int) -> None:
        """
        Re-parent all direct children of an inactive partner to the nearest
        active ancestor (upward compression by one structural link).

        If no active ancestor is found, children become root-level partners.
        """
        node = self._nodes[inactive_partner_id]
        new_upline_id = self._find_nearest_active_upline(inactive_partner_id)

        for child_id in node.downline_ids:
            child_node = self._nodes[child_id]
            # Detach from inactive partner
            child_node.upline_id = new_upline_id

            if new_upline_id is not None:
                self._nodes[new_upline_id].downline_ids.append(child_id)
                self.logger.info(
                    f"Compression: partner {child_id} re-parented "
                    f"from {inactive_partner_id} to {new_upline_id}"
                )
            else:
                self.logger.info(
                    f"Compression: partner {child_id} became root "
                    f"(no active ancestor above {inactive_partner_id})"
                )

        # Clear downline of the inactive node (children have moved)
        node.downline_ids = []

    def _find_nearest_active_upline(self, partner_id: int) -> Optional[int]:
        """
        Walk upline chain until an active partner is found.

        Returns:
            partner_id of the nearest active ancestor, or None.
        """
        current = self._nodes[partner_id].upline_id
        while current is not None:
            if self._nodes[current].is_active:
                return current
            current = self._nodes[current].upline_id
        return None

    # -----------------------------------------------------------------------
    # Commission chain
    # -----------------------------------------------------------------------

    def get_upline_chain(
        self,
        partner_id: int,
        max_levels: int = MAX_LEVELS
    ) -> List[Tuple[int, bool]]:
        """
        Return the upline chain as a list of (partner_id, is_active) tuples.

        This is the exact format consumed by
        CommissionCalculator.calculate_purchase_commissions().

        Args:
            partner_id: The partner who made a purchase.
            max_levels: How many upline levels to include (default: MAX_LEVELS=5).
                        Pass a larger value if needed for extended chains.

        Returns:
            List of (upline_partner_id, is_active) starting from direct upline.
            Length is at most max_levels.
        """
        chain: List[Tuple[int, bool]] = []
        node = self._nodes.get(partner_id)

        if node is None:
            self.logger.warning(f"Partner {partner_id} not found in network")
            return chain

        current_id = node.upline_id
        while current_id is not None and len(chain) < max_levels:
            current_node = self._nodes.get(current_id)
            if current_node is None:
                break
            chain.append((current_id, current_node.is_active))
            current_id = current_node.upline_id

        return chain

    # -----------------------------------------------------------------------
    # Network queries
    # -----------------------------------------------------------------------

    def get_partner(self, partner_id: int) -> Optional[PartnerNode]:
        """Return the PartnerNode for a given ID, or None."""
        return self._nodes.get(partner_id)

    def is_active(self, partner_id: int) -> bool:
        """Check if a partner is active."""
        node = self._nodes.get(partner_id)
        return node.is_active if node else False

    def get_downline(
        self,
        partner_id: int,
        recursive: bool = False
    ) -> List[int]:
        """
        Get direct (or recursive) downline partner IDs.

        Args:
            partner_id: Root partner.
            recursive:  If True, returns all descendants (BFS order).

        Returns:
            List of partner IDs.
        """
        node = self._nodes.get(partner_id)
        if node is None:
            return []

        if not recursive:
            return node.downline_ids.copy()

        # BFS
        result: List[int] = []
        queue = list(node.downline_ids)
        while queue:
            current = queue.pop(0)
            result.append(current)
            child_node = self._nodes.get(current)
            if child_node:
                queue.extend(child_node.downline_ids)
        return result

    def get_level_partners(
        self,
        partner_id: int,
        level: int
    ) -> List[int]:
        """
        Get all partners exactly at a given structural level below partner.

        Args:
            partner_id: Root partner.
            level:      1 = direct downline, 2 = their downline, etc.

        Returns:
            List of partner IDs at that level.
        """
        if level == 0:
            return [partner_id]

        current_level_ids = [partner_id]
        for _ in range(level):
            next_level_ids: List[int] = []
            for pid in current_level_ids:
                n = self._nodes.get(pid)
                if n:
                    next_level_ids.extend(n.downline_ids)
            current_level_ids = next_level_ids

        return current_level_ids

    def get_network_depth(self, partner_id: int) -> int:
        """
        Get maximum structural depth of the sub-network below a partner.

        Returns:
            0 if no downline, otherwise the depth of the deepest branch.
        """
        node = self._nodes.get(partner_id)
        if not node or not node.downline_ids:
            return 0

        return 1 + max(
            self.get_network_depth(child_id)
            for child_id in node.downline_ids
        )

    def get_network_size(self, partner_id: int) -> int:
        """Get total number of partners in the sub-network below a partner."""
        return len(self.get_downline(partner_id, recursive=True))

    def get_network_tree(
        self,
        partner_id: int,
        max_depth: Optional[int] = None
    ) -> Dict:
        """
        Get a nested dict representing the network tree.

        Args:
            partner_id: Root of the subtree.
            max_depth:  Limit recursion depth. None = unlimited.

        Returns:
            Dict with keys 'partner_id', 'is_active', 'children'.
        """
        node = self._nodes.get(partner_id)
        is_active_flag = node.is_active if node else False

        if max_depth == 0 or node is None:
            return {
                'partner_id': partner_id,
                'is_active': is_active_flag,
                'children': []
            }

        children_trees = []
        for child_id in (node.downline_ids if node else []):
            next_depth = None if max_depth is None else max_depth - 1
            children_trees.append(
                self.get_network_tree(child_id, next_depth)
            )

        return {
            'partner_id': partner_id,
            'is_active': is_active_flag,
            'children': children_trees
        }

    def get_all_partner_ids(self) -> Set[int]:
        """Return the set of all registered partner IDs."""
        return set(self._nodes.keys())

    def get_active_partner_ids(self) -> Set[int]:
        """Return the set of all active partner IDs."""
        return {pid for pid, node in self._nodes.items() if node.is_active}
