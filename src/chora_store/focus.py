"""
Focus Manager - Stigmergic Coordination through Focus Marks

Focus is what attention settles on after domain-appropriate sense-making.
It serves as:
- Coordination currency: agents read each other's focus
- Container/attractor: related entities cluster around it
- Recovery mechanism: marks transform "confused" into "complicated"

Focus Properties:
- target: what entity/outcome attention is on
- entry_type: how focus was created (declared | discovered)
- freshness: how long held, when last cycled
- trail: what happened during focus
- provenance: what led here

Focus Lifecycle:
  [discovered|declared] → open → unlocked → [finalize|resume]
                            ↑                      │
                            └──────────────────────┘

- open: Active attention, work in progress
- unlocked: Available for review (TTL passed), requires decision
- finalized: Work cycle complete, trail harvested

Entry Types:
- declared: Agent explicitly commits focus
- discovered: System detects focus from activity
"""

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

from .repository import EntityRepository
from .models import Entity


# Focus lifecycle states
FOCUS_STATUS_OPEN = 'open'
FOCUS_STATUS_UNLOCKED = 'unlocked'  # Was 'stale' - now indicates opportunity for review
FOCUS_STATUS_FINALIZED = 'finalized'

# Legacy alias for backward compatibility
FOCUS_STATUS_STALE = FOCUS_STATUS_UNLOCKED  # Deprecated: use FOCUS_STATUS_UNLOCKED

# Entry types
FOCUS_ENTRY_DECLARED = 'declared'    # Explicit focus creation
FOCUS_ENTRY_DISCOVERED = 'discovered'  # Emerged from activity

# Default TTL for focus (4 hours)
DEFAULT_TTL_MINUTES = 240


@dataclass
class Focus:
    """Represents a focus entity."""
    id: str
    status: str
    data: Dict[str, Any] = field(default_factory=dict)

    @property
    def target(self) -> Optional[str]:
        return self.data.get('target')

    @property
    def agent(self) -> Optional[str]:
        return self.data.get('agent')

    @property
    def trail(self) -> List[str]:
        return self.data.get('trail', [])

    @property
    def provenance(self) -> Optional[str]:
        return self.data.get('provenance')

    @property
    def started_at(self) -> Optional[str]:
        return self.data.get('started_at')


class FocusManager:
    """
    Manages focus lifecycle and coordination.

    Focus is stored as first-class focus entities (type='focus').
    This allows focus marks to be entities in the system,
    discoverable and linkable like any other entity.
    """

    def __init__(self, repository: EntityRepository):
        self.repository = repository

    def create_focus(
        self,
        target_id: str,
        agent: str,
        provenance: Optional[str] = None,
        target_type: Optional[str] = None,
        ttl_minutes: int = DEFAULT_TTL_MINUTES,
        entry_type: str = FOCUS_ENTRY_DECLARED
    ) -> Focus:
        """
        Create a new focus on a target entity (declared entry).

        Args:
            target_id: The entity to focus on
            agent: Identifier for the agent creating focus
            provenance: Optional source (prior focus, inquiry, etc.)
            target_type: 'inquiry', 'goal', or None (auto-detect)
            ttl_minutes: Time before focus becomes unlocked
            entry_type: How focus was created ('declared' | 'discovered')

        Returns:
            Focus object
        """
        now = datetime.utcnow()
        now_iso = now.isoformat()

        # Generate focus ID: focus-{agent}-{target_slug}-{timestamp}
        timestamp = now.strftime("%H%M%S%f")[:12]  # Include microseconds
        target_slug = target_id.split('-')[-1] if '-' in target_id else target_id
        focus_id = f"focus-{agent}-{target_slug}-{timestamp}"

        # Create focus data
        focus_data = {
            'name': f"Focus: {target_id}",
            'description': f"Agent {agent} focusing on {target_id}",
            'target': target_id,
            'agent': agent,
            'entry_type': entry_type,
            'started_at': now_iso,
            'last_cycled': now_iso,
            'ttl_minutes': ttl_minutes,
            'trail': [],
            'provenance': provenance,
            'target_type': target_type or self._detect_target_type(target_id),
            'created': now_iso,
            'updated': now_iso,
        }

        # Create as first-class focus entity (type='focus')
        entity = Entity(
            id=focus_id,
            type='focus',
            status=FOCUS_STATUS_OPEN,  # Focus lifecycle status
            data=focus_data
        )

        self.repository.create(entity)

        return Focus(id=focus_id, status=FOCUS_STATUS_OPEN, data=focus_data)

    def get_focus(self, focus_id: str) -> Optional[Focus]:
        """Get a focus by ID."""
        entity = self.repository.read(focus_id)
        if entity and entity.type == 'focus':
            return Focus(
                id=entity.id,
                status=entity.status,  # Status is now on entity, not in data
                data=entity.data
            )
        return None

    def get_active_focus(self, agent: str) -> Optional[Focus]:
        """Get the currently active (open) focus for an agent."""
        foci = self._list_foci(agent=agent, status=FOCUS_STATUS_OPEN)
        return foci[0] if foci else None

    def discover_focus(
        self,
        target_id: str,
        agent: str,
        activity_source: Optional[str] = None
    ) -> Focus:
        """
        Discover focus from activity (discovered entry).

        Called when system detects an agent working on an entity without
        explicit focus declaration. Focus emerges from activity.

        Args:
            target_id: The entity being worked on
            agent: The agent whose activity was detected
            activity_source: What triggered discovery (e.g., 'entity_touch', 'git_commit')

        Returns:
            Existing open focus if one exists, otherwise creates new discovered focus
        """
        # Check if agent already has open focus on this target
        existing = self._list_foci(agent=agent, status=FOCUS_STATUS_OPEN)
        for focus in existing:
            if focus.data.get('target') == target_id:
                # Already focused, just update last_cycled
                entity = self.repository.read(focus.id)
                if entity:
                    entity.data['last_cycled'] = datetime.utcnow().isoformat()
                    if activity_source:
                        activities = entity.data.get('activity_sources', [])
                        if activity_source not in activities:
                            activities.append(activity_source)
                        entity.data['activity_sources'] = activities
                    self.repository.update(entity)
                return focus

        # No existing focus, create discovered focus
        return self.create_focus(
            target_id=target_id,
            agent=agent,
            entry_type=FOCUS_ENTRY_DISCOVERED,
            provenance=activity_source
        )

    def mark_unlocked(self, focus_id: str) -> Focus:
        """
        Mark a focus as unlocked (available for review).

        Unlocked focus requires decision: resume or finalize.
        This is an opportunity, not a failure state.
        """
        entity = self.repository.read(focus_id)
        if entity:
            entity.status = FOCUS_STATUS_UNLOCKED  # Update entity status
            entity.data['unlocked_at'] = datetime.utcnow().isoformat()
            entity.data['updated'] = datetime.utcnow().isoformat()
            self.repository.update(entity)
            return Focus(id=focus_id, status=FOCUS_STATUS_UNLOCKED, data=entity.data)
        raise ValueError(f"Focus not found: {focus_id}")

    # Deprecated alias for backward compatibility
    def mark_stale(self, focus_id: str) -> Focus:
        """Deprecated: Use mark_unlocked instead."""
        return self.mark_unlocked(focus_id)

    def resume_focus(self, focus_id: str) -> Focus:
        """
        Resume an unlocked focus (return to open state).

        Used when agent decides to continue working on an unlocked focus
        rather than finalizing it.
        """
        entity = self.repository.read(focus_id)
        if entity:
            if entity.status != FOCUS_STATUS_UNLOCKED:
                raise ValueError(f"Can only resume unlocked focus, got: {entity.status}")
            entity.status = FOCUS_STATUS_OPEN  # Update entity status
            entity.data['resumed_at'] = datetime.utcnow().isoformat()
            entity.data['last_cycled'] = datetime.utcnow().isoformat()
            entity.data['updated'] = datetime.utcnow().isoformat()
            self.repository.update(entity)
            return Focus(id=focus_id, status=FOCUS_STATUS_OPEN, data=entity.data)
        raise ValueError(f"Focus not found: {focus_id}")

    def finalize_focus(self, focus_id: str) -> Dict[str, Any]:
        """
        Finalize a focus - harvest trail and archive.

        Returns dict with harvested information.
        """
        entity = self.repository.read(focus_id)
        if not entity:
            raise ValueError(f"Focus not found: {focus_id}")

        # Harvest trail
        trail = entity.data.get('trail', [])
        harvested = {
            'focus_id': focus_id,
            'target': entity.data.get('target'),
            'trail': trail,
            'trail_count': len(trail),
            'duration': self._calculate_duration(entity.data),
            'finalized_at': datetime.utcnow().isoformat()
        }

        # Update status
        entity.status = FOCUS_STATUS_FINALIZED  # Update entity status
        entity.data['finalized_at'] = harvested['finalized_at']
        entity.data['harvested'] = harvested
        self.repository.update(entity)

        return harvested

    def add_to_trail(
        self,
        focus_id: str,
        entity_id: str,
        entity_type: Optional[str] = None
    ) -> None:
        """Add an entity to the focus trail."""
        entity = self.repository.read(focus_id)
        if entity:
            trail = entity.data.get('trail', [])
            if entity_id not in trail:
                trail.append(entity_id)
                entity.data['trail'] = trail
                entity.data['last_cycled'] = datetime.utcnow().isoformat()
                self.repository.update(entity)

    def shift_focus(
        self,
        old_focus_id: str,
        new_target_id: str,
        agent: str
    ) -> Focus:
        """
        Shift focus from one target to another.
        Unlocks old focus and opens new one.
        """
        # Unlock old focus (available for review/pickup)
        self.mark_unlocked(old_focus_id)

        # Create new focus with provenance
        return self.create_focus(
            target_id=new_target_id,
            agent=agent,
            provenance=old_focus_id
        )

    def check_and_mark_unlocked(self) -> List[str]:
        """
        Check all open foci and mark unlocked ones (TTL expired).
        Returns list of focus IDs that became unlocked.
        """
        unlocked_ids = []
        open_foci = self._list_foci(status=FOCUS_STATUS_OPEN)
        now = datetime.utcnow()

        for focus in open_foci:
            ttl_minutes = focus.data.get('ttl_minutes', DEFAULT_TTL_MINUTES)
            last_cycled = focus.data.get('last_cycled') or focus.data.get('started_at')

            if last_cycled:
                last_cycled_dt = datetime.fromisoformat(last_cycled.replace('Z', '+00:00').replace('+00:00', ''))
                if now - last_cycled_dt > timedelta(minutes=ttl_minutes):
                    self.mark_unlocked(focus.id)
                    unlocked_ids.append(focus.id)

        return unlocked_ids

    # Deprecated alias
    def check_and_mark_stale(self) -> List[str]:
        """Deprecated: Use check_and_mark_unlocked instead."""
        return self.check_and_mark_unlocked()

    def get_awareness_candidates(self, agent: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get foci that should be surfaced in orient.
        Returns open and unlocked foci (unfinalized).

        This is the stigmergic read - seeing what others are focused on.
        """
        candidates = []

        # Get open foci (active work)
        for focus in self._list_foci(status=FOCUS_STATUS_OPEN):
            candidates.append({
                'id': focus.id,
                'target': focus.target,
                'agent': focus.agent,
                'status': FOCUS_STATUS_OPEN,
                'entry_type': focus.data.get('entry_type', FOCUS_ENTRY_DECLARED),
                'started_at': focus.started_at,
                'is_own': focus.agent == agent
            })

        # Get unlocked foci (need decision: resume or finalize)
        for focus in self._list_foci(status=FOCUS_STATUS_UNLOCKED):
            candidates.append({
                'id': focus.id,
                'target': focus.target,
                'agent': focus.agent,
                'status': FOCUS_STATUS_UNLOCKED,
                'entry_type': focus.data.get('entry_type', FOCUS_ENTRY_DECLARED),
                'started_at': focus.started_at,
                'is_own': focus.agent == agent,
                'needs_decision': True  # Resume or finalize?
            })

        return candidates

    def recover_focus(self, target_id: str, agent: str) -> Optional[Focus]:
        """
        Recover focus on a target - find previous focus and create continuation.

        Looks for unlocked or finalized foci on the target. For unlocked foci,
        consider using resume_focus instead if you want to continue the same focus.
        """
        # Find unlocked or finalized focus on this target
        # Need to check all statuses including finalized
        unlocked_foci = self._list_foci(status=FOCUS_STATUS_UNLOCKED)
        finalized_foci = self._list_foci(status=FOCUS_STATUS_FINALIZED)
        all_foci = unlocked_foci + finalized_foci
        previous = None

        for focus in all_foci:
            if focus.target == target_id:
                previous = focus
                break

        if previous:
            # Create new focus with link to previous
            new_focus = self.create_focus(
                target_id=target_id,
                agent=agent,
                provenance=previous.id
            )
            # Copy trail reference
            new_focus.data['prior_focus'] = previous.id
            new_focus.data['inherited_trail'] = previous.trail

            entity = self.repository.read(new_focus.id)
            entity.data = new_focus.data
            self.repository.update(entity)

            return new_focus

        return None

    def reopen_focus(self, target_id: str, agent: str) -> Focus:
        """
        Reopen focus on a target after finalization.
        For inquiries: natural continuation (exploration often reopens).
        For goals: signals potential inquiry-in-disguise.

        Note: For unlocked focus, prefer resume_focus to continue the same focus.
        This method creates a NEW focus linked to a previous finalized one.
        """
        # Find previous finalized focus on this target
        finalized_foci = self._list_foci(status=FOCUS_STATUS_FINALIZED)
        previous = None

        for focus in finalized_foci:
            if focus.target == target_id:
                previous = focus
                break

        if not previous:
            # No previous focus, just create new
            return self.create_focus(target_id, agent)

        # Check target type
        target_type = previous.data.get('target_type', 'unknown')
        close_reason = previous.data.get('close_reason')

        # Create new focus
        new_focus = self.create_focus(
            target_id=target_id,
            agent=agent,
            provenance=previous.id,
            target_type=target_type
        )

        # Link to prior
        entity = self.repository.read(new_focus.id)
        entity.data['prior_focus'] = previous.id

        # Signal if goal being reopened after condition-based closure
        if target_type == 'goal' and close_reason == 'condition_met':
            entity.data['signal'] = 'inquiry_in_disguise'
            entity.data['signal_reason'] = 'Goal reopened after condition-based finalization'

        self.repository.update(entity)

        return Focus(id=new_focus.id, status=FOCUS_STATUS_OPEN, data=entity.data)

    def _list_foci(
        self,
        agent: Optional[str] = None,
        status: Optional[str] = None
    ) -> List[Focus]:
        """List focus entities, optionally filtered."""
        # Get all focus entities (type='focus')
        focus_entities = self.repository.list('focus')
        foci = []

        for entity in focus_entities:
            focus_status = entity.status  # Status is on entity now
            focus_agent = entity.data.get('agent')

            # Apply filters
            if status and focus_status != status:
                continue
            if agent and focus_agent != agent:
                continue

            foci.append(Focus(
                id=entity.id,
                status=focus_status,
                data=entity.data
            ))

        return foci

    def _update_status(self, focus_id: str, new_status: str) -> Focus:
        """Update focus status."""
        entity = self.repository.read(focus_id)
        if entity:
            entity.status = new_status  # Update entity status
            entity.data['updated'] = datetime.utcnow().isoformat()
            self.repository.update(entity)
            return Focus(id=focus_id, status=new_status, data=entity.data)
        raise ValueError(f"Focus not found: {focus_id}")

    def _detect_target_type(self, target_id: str) -> str:
        """Detect if target is inquiry-like or goal-like."""
        if target_id.startswith('inquiry-'):
            return 'inquiry'
        elif target_id.startswith('feature-') or target_id.startswith('task-'):
            return 'goal'
        elif target_id.startswith('release-'):
            return 'release'
        return 'unknown'

    def _calculate_duration(self, focus_data: Dict[str, Any]) -> Optional[str]:
        """Calculate focus duration."""
        started = focus_data.get('started_at')
        if started:
            start_dt = datetime.fromisoformat(started.replace('Z', '+00:00').replace('+00:00', ''))
            duration = datetime.utcnow() - start_dt
            hours = duration.total_seconds() / 3600
            if hours < 1:
                return f"{int(duration.total_seconds() / 60)} minutes"
            return f"{hours:.1f} hours"
        return None
