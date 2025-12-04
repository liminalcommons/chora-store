"""
Wave 8: Metabolic Cycle Activation - Entity Creation

Creates the foundational entities for compound leverage activation:
- tool-propose-pattern (first generative tool)
- Learning entities capturing insights
- Feature entity for governance

Run with:
    PYTHONPATH=packages/chora-store/src python3 -m chora_store.migrations.wave8_metabolic_activation
"""

from chora_store.factory import EntityFactory
from chora_store.repository import EntityRepository


def create_wave8_entities():
    """Create Wave 8 foundational entities."""
    repo = EntityRepository()
    factory = EntityFactory(repository=repo)

    entities_created = []

    # =========================================================================
    # LEARNING: Compound vs Additive Leverage
    # =========================================================================
    try:
        learning1 = factory.create(
            'learning',
            'Compound vs Additive Leverage',
            insight='''Activating existing mechanisms is multiplicative (compound),
            adding new infrastructure is additive. The system already has L5 generative
            handlers, route crystallization, autonomous reification hooks, and tool
            cognition lifecycle patterns. These need activation, not addition.''',
            context='Discovered while planning Wave 8 metabolic cycle activation',
            domain='system-design',
            implications=[
                'Prefer activation over creation',
                'Existing infrastructure may be more powerful than realized',
                'Compound leverage enables self-extension',
            ],
            source='planning',
            links=['inquiry-metabolic-cycle-operational'],
        )
        entities_created.append(learning1.id)
        print(f"  Created: {learning1.id}")
    except Exception as e:
        print(f"  Skip (exists?): learning-compound-vs-additive-leverage - {e}")

    # =========================================================================
    # LEARNING: Autopoietic Loop Has Gaps
    # =========================================================================
    try:
        learning2 = factory.create(
            'learning',
            'Autopoietic Loop Has Gaps',
            insight='''The autopoietic governance loop (Pattern -> Tool -> Observation ->
            Learning -> Pattern) is architecturally present but operationally open.
            Gaps: No generative tool entities exist, traces not analyzed, surprises
            not surfaced, induction not auto-invoked.''',
            context='Discovered during exploration of existing metabolic infrastructure',
            domain='system-architecture',
            implications=[
                'Each gap blocks compound leverage',
                'Closing gaps enables self-extending behavior',
                'Pattern->Tool link is the keystone (highest leverage)',
            ],
            source='code_review',
            links=['inquiry-metabolic-cycle-operational'],
        )
        entities_created.append(learning2.id)
        print(f"  Created: {learning2.id}")
    except Exception as e:
        print(f"  Skip (exists?): learning-autopoietic-loop-has-gaps - {e}")

    # =========================================================================
    # LEARNING: Dogfooding Gaps in Orient
    # =========================================================================
    try:
        learning3 = factory.create(
            'learning',
            'Dogfooding Gaps in Orient',
            insight='''Orient hardcodes ~400 lines of reporting logic instead of
            invoking tools. Could invoke tool-induction, tool-suggest-patterns,
            and other tools for composition. Tool invocations would generate
            traces that feed route crystallization.''',
            context='Discovered analyzing cli.py orient() function',
            domain='dogfooding',
            implications=[
                'Orient should invoke tools for composition',
                'Tool invocations create traces',
                'Traces compound into routes',
                'Self-aware orient would demonstrate tools all the way down',
            ],
            source='code_review',
            links=['inquiry-metabolic-cycle-operational'],
        )
        entities_created.append(learning3.id)
        print(f"  Created: {learning3.id}")
    except Exception as e:
        print(f"  Skip (exists?): learning-dogfooding-gaps-in-orient - {e}")

    # =========================================================================
    # TOOL: Propose Pattern (First Generative Tool)
    # =========================================================================
    try:
        tool = factory.create(
            'tool',
            'Propose Pattern from Cluster',
            handler={
                'type': 'generative',
                'prompt_template': '''Analyze these clustered learnings and generate a pattern proposal.

LEARNINGS:
{{ learnings }}

EXISTING PATTERNS (for reference):
{{ patterns }}

Generate a pattern proposal as YAML with this exact structure:

```yaml
id: pattern-{your-proposed-slug}
type: pattern
subtype: behavioral
status: proposed
name: "Pattern Name"
description: |
  What this pattern captures - the wisdom hiding in the learnings.
context: |
  When this pattern applies - the situation that calls for it.
mechanics:
  target: {entity_type_this_applies_to}
  # Optional: inject_fields, hooks, etc.
fitness:
  observation_period: "30 days"
  success_signals:
    - Observable behavior 1
    - Observable behavior 2
```

Output ONLY the YAML block, no explanation before or after.
The pattern should crystallize the wisdom from the learnings into reusable guidance.''',
                'system_prompt': '''You are a pattern crystallizer for the chora system.
Your role is to find the wisdom hiding in accumulated learnings and crystallize it into
reusable patterns. Patterns capture "what works" so future agents can benefit.

Be specific and concrete. Good patterns have:
- Clear names that evoke recognition
- Specific contexts (not "use when appropriate")
- Concrete mechanics (not abstract principles)
- Observable fitness signals''',
                'output_type': 'pattern',
                'approval_required': True,
                'model': 'sonnet',
            },
            interfaces=['mcp', 'cli'],
            description='Generate pattern proposal from clustered learnings',
            when_to_use='When induction shows a strong cluster that wants to become a pattern',
            inputs=[
                {'name': 'learnings', 'type': 'array', 'required': True,
                 'description': 'List of learning IDs or learning summaries to synthesize'},
            ],
            cognition={
                'ready_at_hand': '''Induction showed a strong cluster. Multiple learnings
                    are saying similar things from different angles. The wisdom is there,
                    waiting to be crystallized into a reusable pattern. Time to propose.''',
                'vignette': '''You've run induction and it shows 5 learnings clustering
                    around "entity validation". Each learning captures a piece of the
                    puzzle - when validation should happen, what makes it effective,
                    what breaks. You invoke propose-pattern with those learnings.
                    It generates a pattern-structural-validation proposal that captures
                    the crystallized wisdom.''',
                'not_when': [
                    'Cluster has fewer than 3 learnings - not enough signal',
                    'Learnings are about completely different things - no coherent pattern',
                    'Pattern already exists - link learnings to it instead',
                    'You want to create the pattern manually - do that directly',
                ],
                'breakdown': {
                    'signals': [
                        'Generated pattern is too abstract or generic',
                        'Pattern mechanics are vague ("apply when appropriate")',
                        'Same pattern keeps being proposed - not synthesizing',
                    ],
                    'recovery': '''If patterns are too abstract, the learnings may
                        be too diverse. Try with a smaller, more focused cluster.
                        If mechanics are vague, the learnings may lack concrete detail.'''
                },
                'flow': {
                    'leads_to': [],
                    'receives_from': ['tool-induction'],
                },
                'phase': 'check',
                'discernment': {
                    'clarity': 'medium',
                    'stakes': 'medium',
                    'just_do_it': False,  # Requires cluster first
                },
                'core': False,
                'cognitive_status': 'experimental',
                'origin': 'feature-metabolic-cycle-activation',
            },
        )
        entities_created.append(tool.id)
        print(f"  Created: {tool.id}")
    except Exception as e:
        print(f"  Skip (exists?): tool-propose-pattern-from-cluster - {e}")

    # =========================================================================
    # FEATURE: Metabolic Cycle Activation (Governance)
    # =========================================================================
    try:
        feature = factory.create(
            'feature',
            'Metabolic Cycle Activation',
            description='''Activates compound leverage mechanisms to close the autopoietic
            loop: Pattern -> Tool -> Observation -> Learning -> Pattern. Rather than
            adding new infrastructure, this activates existing mechanisms: generative
            handlers, route crystallization, induction automation, and tool emergence.''',
            origin='inquiry-metabolic-cycle-operational',
            behaviors=[
                {
                    'id': 'behavior-generative-tool-creates-patterns',
                    'description': 'tool-propose-pattern generates pattern proposals from learning clusters',
                    'given': 'A cluster of 3+ related learnings exists',
                    'when': 'tool-propose-pattern is invoked with those learnings',
                    'then': 'A pattern proposal YAML is generated for approval',
                    'status': 'untested',
                },
                {
                    'id': 'behavior-orient-surfaces-crystallization',
                    'description': 'Orient shows route crystallization candidates',
                    'given': 'Traces exist with matching signatures and high consistency',
                    'when': 'Orient runs',
                    'then': 'Crystallization candidates are surfaced in output',
                    'status': 'untested',
                },
                {
                    'id': 'behavior-orient-uses-tools',
                    'description': 'Orient invokes tools rather than hardcoding logic',
                    'given': 'Orient is configured for tool dogfooding',
                    'when': 'Orient runs',
                    'then': 'Tool invocations generate traces for crystallization',
                    'status': 'untested',
                },
                {
                    'id': 'behavior-induction-auto-triggers',
                    'description': 'Induction auto-invokes when learning threshold met',
                    'given': '5+ captured learnings exist',
                    'when': 'A new learning is created',
                    'then': 'tool-induction is auto-invoked via epigenetic hook',
                    'status': 'untested',
                },
                {
                    'id': 'behavior-pattern-to-tool-evaluation',
                    'description': 'Adopted patterns trigger tool emergence evaluation',
                    'given': 'A pattern reaches adopted status',
                    'when': 'Status transition completes',
                    'then': 'tool-notice-emerging-tools is invoked to evaluate tool candidacy',
                    'status': 'untested',
                },
            ],
            links=[
                'learning-compound-vs-additive-leverage',
                'learning-autopoietic-loop-has-gaps',
                'learning-dogfooding-gaps-in-orient',
            ],
        )
        entities_created.append(feature.id)
        print(f"  Created: {feature.id}")
    except Exception as e:
        print(f"  Skip (exists?): feature-metabolic-cycle-activation - {e}")

    # =========================================================================
    # INQUIRY: Metabolic Cycle as Operational (captures the original question)
    # =========================================================================
    try:
        inquiry = factory.create(
            'inquiry',
            'Metabolic Cycle Operational Not Aspirational',
            question='''The system can digest but digestion doesn't happen. How do we
            move from aspirational (the infrastructure exists) to operational (the
            cycle actually runs)?''',
            context='''Observed that many learnings and features accumulate without
            being finalized. The autophagic cycle hasn't "just worked" to digest
            changes and propagate leverage. Orient surfaces issues but digestion
            doesn't complete.''',
            status='active',
            exploration_notes=[
                'Existing inquiry: inquiry-learning-lifecycle-evolution addresses part of this',
                'Infrastructure exists: MetabolicEngine, RouteTable, PatternInductor',
                'Gap: cron:daily hooks only fire on manual orient',
                'Gap: No generative tool entities exist (tools that create tools)',
                'Gap: Route crystallization exists but not wired to orient',
            ],
            links=['inquiry-learning-lifecycle-evolution'],
        )
        entities_created.append(inquiry.id)
        print(f"  Created: {inquiry.id}")
    except Exception as e:
        print(f"  Skip (exists?): inquiry-metabolic-cycle-operational - {e}")

    print(f"\nTotal entities created: {len(entities_created)}")
    print("Entities:", entities_created)
    return entities_created


if __name__ == '__main__':
    print("Wave 8: Creating foundational entities...")
    print("=" * 60)
    create_wave8_entities()
    print("=" * 60)
    print("Done.")
