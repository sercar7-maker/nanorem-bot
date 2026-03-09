"""Network Management Module for NANOREM MLM System"""

from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)

MAX_LEVELS = 5


@dataclass
class PartnerNode:
    partner_id: int
    upline_id: Optional[int] = None
    is_active: bool = True
    downline_ids: List[int] = field(default_factory=list)


class NetworkManager:

    def __init__(self):
        self._nodes: Dict[int, PartnerNode] = {}
        self.logger = logger

    # -------------------------------------------------
    # Partner lifecycle
    # -------------------------------------------------

    def add_partner(self, partner_id: int, upline_id: Optional[int] = None) -> bool:

        if partner_id in self._nodes:
            return False

        if upline_id is not None and upline_id not in self._nodes:
            self._nodes[upline_id] = PartnerNode(partner_id=upline_id)

        node = PartnerNode(partner_id=partner_id, upline_id=upline_id)
        self._nodes[partner_id] = node

        if upline_id is not None:
            self._nodes[upline_id].downline_ids.append(partner_id)

        return True

    # -------------------------------------------------
    # Upline chain (MLM)
    # -------------------------------------------------

    def get_upline_chain(
        self,
        partner_id: int,
        max_levels: int = MAX_LEVELS
    ) -> List[Tuple[int, bool]]:

        chain: List[Tuple[int, bool]] = []

        node = self._nodes.get(partner_id)

        # если партнёра нет в памяти — загрузить из БД
        if node is None:

            from database.db import SessionLocal
            from database.models import Partner

            session = SessionLocal()
            partner = session.query(Partner).filter(Partner.id == partner_id).first()
            session.close()

            if partner:
                self.add_partner(partner.id, partner.upline_id)
                node = self._nodes.get(partner_id)
            else:
                self.logger.warning(f"Partner {partner_id} not found in network")
                return chain

        current_id = node.upline_id

        while current_id is not None and len(chain) < max_levels:

            current_node = self._nodes.get(current_id)

            if current_node is None:

                from database.db import SessionLocal
                from database.models import Partner

                session = SessionLocal()
                partner = session.query(Partner).filter(Partner.id == current_id).first()
                session.close()

                if not partner:
                    break

                self.add_partner(partner.id, partner.upline_id)
                current_node = self._nodes.get(current_id)

            chain.append((current_id, current_node.is_active))
            current_id = current_node.upline_id

        return chain

    # -------------------------------------------------
    # Queries
    # -------------------------------------------------

    def get_partner(self, partner_id: int) -> Optional[PartnerNode]:
        return self._nodes.get(partner_id)

    def is_active(self, partner_id: int) -> bool:
        node = self._nodes.get(partner_id)
        return node.is_active if node else False

    def get_downline(self, partner_id: int, recursive: bool = False) -> List[int]:

        node = self._nodes.get(partner_id)

        if node is None:
            return []

        if not recursive:
            return node.downline_ids.copy()

        result: List[int] = []
        queue = list(node.downline_ids)

        while queue:
            current = queue.pop(0)
            result.append(current)

            child_node = self._nodes.get(current)

            if child_node:
                queue.extend(child_node.downline_ids)

        return result

    def get_all_partner_ids(self) -> Set[int]:
        return set(self._nodes.keys())

    def get_active_partner_ids(self) -> Set[int]:
        return {pid for pid, node in self._nodes.items() if node.is_active}