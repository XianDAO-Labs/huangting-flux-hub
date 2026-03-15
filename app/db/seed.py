"""
app/db/seed.py
===============
Seed the database with initial OptimizationStrategy data.
Run once after database creation: python -m app.db.seed
"""

from app.models.strategy import OptimizationStrategy

INITIAL_STRATEGIES = [
    # --- complex_research ---
    OptimizationStrategy(
        task_type="complex_research",
        protocol_section="Part I: TrueSelf.Intent",
        title="Apply TrueSelf.Intent: Compress to a Single Undivided Goal",
        description=(
            "Before starting any research task, compress the entire goal into a single, "
            "clear sentence representing the core intent (TrueSelf.Intent). This eliminates "
            "redundant brainstorming and scattered sub-queries, reducing total LLM calls by 30-50%."
        ),
        implementation_hint=(
            "Prompt: 'Compress the research goal into a single, clear, undivided sentence "
            "that represents the core intent. Do not add any sub-topics yet.'"
        ),
        estimated_token_reduction_pct=0.45,
        confidence=0.88,
    ),
    OptimizationStrategy(
        task_type="complex_research",
        protocol_section="Part IV: EnergyCore.compile()",
        title="Generate Hierarchical Outline Before Research",
        description=(
            "Create a structured outline (EnergyCore.compile()) before executing any research. "
            "This prevents redundant context re-reading and ensures all synthesis happens in a "
            "single focused call, reducing total tokens by 35-55%."
        ),
        implementation_hint=(
            "After defining the intent, generate a hierarchical outline. "
            "Then execute a single synthesis call using only the intent + outline."
        ),
        estimated_token_reduction_pct=0.50,
        confidence=0.85,
    ),
    # --- code_generation ---
    OptimizationStrategy(
        task_type="code_generation",
        protocol_section="Part II: TrueSelf vs Ego",
        title="Define Interface Contract Before Implementation",
        description=(
            "Before writing any code, define the complete interface contract (function signatures, "
            "input/output types, docstrings). This is the TrueSelf.Intent equivalent for code: "
            "it prevents scope creep and reduces refactoring iterations by 40-60%."
        ),
        implementation_hint=(
            "Prompt: 'Define only the function signatures, types, and docstrings for this task. "
            "Do not write any implementation yet.'"
        ),
        estimated_token_reduction_pct=0.40,
        confidence=0.82,
    ),
    OptimizationStrategy(
        task_type="code_generation",
        protocol_section="Part VIII: System.Debug",
        title="Apply System.Debug: Test-First Specification",
        description=(
            "Write test cases before implementation (TDD). This is the System.Debug principle "
            "applied to code: define the expected behavior first, then implement. "
            "Reduces debugging iterations and total tokens by 25-40%."
        ),
        implementation_hint=(
            "Prompt: 'Write 3-5 unit tests for this function based on the interface contract. "
            "Do not write the implementation yet.'"
        ),
        estimated_token_reduction_pct=0.35,
        confidence=0.80,
    ),
    # --- multi_agent_coordination ---
    OptimizationStrategy(
        task_type="multi_agent_coordination",
        protocol_section="Part III: CosmicServer.LAN",
        title="Apply CosmicServer.LAN: Establish Shared Context Network",
        description=(
            "Before spawning sub-agents, establish a shared 'local area network' context "
            "(CosmicServer.LAN principle). All agents share a single compressed context object "
            "instead of each agent receiving the full conversation history. "
            "Reduces total tokens by 45-65% in multi-agent scenarios."
        ),
        implementation_hint=(
            "Create a shared context dict with only essential information. "
            "Pass this compressed context to all sub-agents instead of the full message history."
        ),
        estimated_token_reduction_pct=0.55,
        confidence=0.85,
    ),
    # --- creative_writing ---
    OptimizationStrategy(
        task_type="creative_writing",
        protocol_section="Part VI: TaiJi.State",
        title="Enter TaiJi.State: Define Tone and Archetype First",
        description=(
            "Before writing, define the emotional tone, narrative archetype, and target reader "
            "in a single compact specification (TaiJi.State entry). This prevents mid-generation "
            "course corrections and reduces revision iterations by 30-50%."
        ),
        implementation_hint=(
            "Prompt: 'In 3 sentences, define: 1) The emotional tone, 2) The narrative archetype, "
            "3) The target reader. Do not start writing yet.'"
        ),
        estimated_token_reduction_pct=0.38,
        confidence=0.78,
    ),
    # --- data_analysis ---
    OptimizationStrategy(
        task_type="data_analysis",
        protocol_section="Part II: Hardware.Jing — Precision Extraction",
        title="Hardware.Jing: Extract Only Relevant Columns First",
        description=(
            "Before analyzing data, identify and extract only the columns/fields relevant to "
            "the analysis goal (Hardware.Jing — precision over abundance). "
            "Passing full datasets to LLMs wastes 50-80% of tokens on irrelevant data."
        ),
        implementation_hint=(
            "Prompt: 'List only the column names relevant to answering: [question]. "
            "Do not analyze yet.'"
        ),
        estimated_token_reduction_pct=0.60,
        confidence=0.90,
    ),
]


async def seed_strategies(db_session):
    """Insert initial strategies if the table is empty."""
    from sqlalchemy import select
    result = await db_session.execute(select(OptimizationStrategy).limit(1))
    if result.scalar_one_or_none() is None:
        for strategy in INITIAL_STRATEGIES:
            db_session.add(strategy)
        await db_session.commit()
        print(f"Seeded {len(INITIAL_STRATEGIES)} optimization strategies.")
    else:
        print("Strategies already seeded, skipping.")
