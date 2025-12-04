Feature: Tiered Resolution
  The push-right pattern for synthesis operations. Operations try cheaper tiers
  first and escalate when needed. All tier attempts capture traces for future
  crystallization.

  Background:
    Given a fresh repository

  Scenario: Workflow tier synthesis succeeds with high confidence
    Given multiple learnings with high keyword overlap
    When tiered_synthesize is called with the learning IDs
    Then synthesis succeeds at the workflow tier
    And a trace is captured for the workflow tier

  Scenario: Workflow tier escalates to inference on low confidence
    Given multiple learnings with low keyword overlap
    When tiered_synthesize is called with the learning IDs
    Then synthesis escalates to inference tier
    And traces are captured for both workflow and inference tiers

  Scenario: Max tier constraint is respected
    Given multiple learnings with low keyword overlap
    When tiered_synthesize is called with max_tier "workflow"
    Then synthesis does not escalate beyond workflow
    And an escalation reason is provided

  Scenario: Insufficient learnings returns early
    Given only one learning
    When tiered_synthesize is called with the learning IDs
    Then synthesis fails with an error about insufficient learnings
    And no traces are captured

  Scenario: Trace captures operation details
    Given multiple learnings with high keyword overlap
    When tiered_synthesize is called with the learning IDs
    Then the trace includes operation_type "synthesize"
    And the trace includes the input learning IDs
    And the trace includes reasoning steps

  # ═══════════════════════════════════════════════════════════════════════════
  # Tool Invocation Tier Assignment
  # ═══════════════════════════════════════════════════════════════════════════

  Scenario: LLM handler tool traces at inference tier
    Given an LLM handler tool exists
    When the tool is invoked
    Then the trace is captured with tier "inference"

  Scenario: Reference handler tool traces at workflow tier
    Given a reference handler tool exists
    When the tool is invoked
    Then the trace is captured with tier "workflow"

  Scenario: Generative handler tool traces at inference tier
    Given a generative handler tool exists
    When the tool is invoked
    Then the trace is captured with tier "inference"

  # ═══════════════════════════════════════════════════════════════════════════
  # Semantic Trace Clustering (Embedding-Based)
  # ═══════════════════════════════════════════════════════════════════════════

  Scenario: Similar traces are clustered by embedding similarity
    Given 5 traces with similar inputs about "agent awareness"
    When trace clustering is triggered for the tool
    Then traces are grouped by embedding similarity
    And clusters use EmbeddingService with threshold 0.90

  Scenario: Dissimilar traces form separate clusters
    Given traces with diverse inputs
    When trace clustering is triggered
    Then dissimilar traces are not grouped together
    And each cluster contains semantically related traces only

  # ═══════════════════════════════════════════════════════════════════════════
  # Route Crystallization
  # ═══════════════════════════════════════════════════════════════════════════

  Scenario: Route is crystallized from consistent trace cluster
    Given a trace cluster with 5+ traces
    And the cluster has output consistency above 0.95
    When route crystallization is triggered
    Then a route entity is created
    And the route contains input_signature from cluster centroid
    And the route contains cached_output from most common output

  Scenario: Route crystallization requires minimum traces
    Given a trace cluster with only 3 traces
    When route crystallization is attempted
    Then no route is created
    And traces remain for future clustering

  Scenario: Crystallized route is used for future lookups
    Given a route exists for input pattern "orient default"
    When a matching input is received
    Then the cached output is returned
    And no tool invocation occurs
    And the resolution tier is "data"

  # ═══════════════════════════════════════════════════════════════════════════
  # Provider Selection for Trace Clustering
  # ═══════════════════════════════════════════════════════════════════════════

  Scenario: Local embeddings are used by default for clustering
    Given no OPENAI_API_KEY is set
    When trace clustering is performed
    Then the local embedding provider is used

  Scenario: OpenAI embeddings are used when configured
    Given OPENAI_API_KEY is set
    And embedding provider is configured as "openai"
    When trace clustering is performed
    Then the OpenAI embedding provider is used

  # ═══════════════════════════════════════════════════════════════════════════
  # Provider-Aware Threshold Defaults
  # ═══════════════════════════════════════════════════════════════════════════

  Scenario: EmbeddingService exposes provider-specific default thresholds
    When EmbeddingService is queried for default thresholds
    Then local provider has similarity threshold 0.65
    And local provider has clustering threshold 0.70
    And openai provider has similarity threshold 0.80
    And openai provider has clustering threshold 0.85

  Scenario: Default threshold is used when none specified
    Given local embedding provider is active
    When clustering is performed without explicit threshold
    Then the provider's default clustering threshold is used

  Scenario: Explicit threshold overrides provider default
    Given local embedding provider is active
    When clustering is performed with explicit threshold 0.90
    Then the explicit threshold 0.90 is used

  # ═══════════════════════════════════════════════════════════════════════════
  # Auto-Crystallization Hook
  # ═══════════════════════════════════════════════════════════════════════════

  Scenario: Auto-crystallization runs on cron trigger
    Given 10 traces exist for a tool with consistent outputs
    When auto_crystallize cron hook is triggered
    Then routes are created for eligible trace clusters
    And a learning is emitted about crystallization

  Scenario: Auto-crystallization skips tools with insufficient traces
    Given only 3 traces exist for a tool
    When auto_crystallize cron hook is triggered
    Then no routes are created
    And traces remain for future crystallization

  # ═══════════════════════════════════════════════════════════════════════════
  # Routes Teaching Back (Metabolic Loop Closure)
  # ═══════════════════════════════════════════════════════════════════════════

  Scenario: Successful route generates learning about crystallizability
    Given a route with 10+ hits
    When route success is evaluated
    Then a learning is generated about what crystallized well
    And the learning has domain "metabolic"
    And the learning references the route in its context

  Scenario: Route success learning captures crystallization signature
    Given a route with high hit count for "orient" operations
    When route success is evaluated
    Then the learning captures input_signature characteristics
    And the learning captures output_template patterns
    And the learning has tag "crystallization-success"

  Scenario: Multiple route learnings cluster into meta-pattern
    Given 5 route-success learnings about different tools
    When pattern induction is run on crystallization learnings
    Then a meta-pattern proposal is generated
    And the meta-pattern describes "what makes operations crystallizable"
    And the meta-pattern has subtype "meta"

  Scenario: Route teaching back is triggered periodically
    Given multiple routes with hit_count above threshold
    When route_teach_back cron hook is triggered
    Then learnings are generated for qualifying routes
    And routes are marked as having generated learnings

  Scenario: Routes only teach back once per threshold
    Given a route that has already generated a learning at 10 hits
    When the route reaches 20 hits
    Then a second learning is generated for the new threshold
    And the learning notes continued success

  Scenario: Low-performing routes do not generate learnings
    Given a route with high miss_count relative to hit_count
    When route success is evaluated
    Then no learning is generated
    And the route is flagged for review
