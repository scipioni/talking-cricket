import pytest
import datetime as dt
import json
from calobot.settings import get_settings
from harness.scenario import Scenario, Persona, Step, NothingStored
from harness.simulation import run_scenario
from harness.user_agent import SimulatedUser
from calobot.llm.gateway import LLMGateway

SCENARIOS_DATA = [
    {"persona": "hurried", "intent": "logs 80g of blueberries", "behaviour": "straight"},
    {"persona": "curious", "intent": "asks what to eat for dinner", "behaviour": "straight"},
    {"persona": "tired", "intent": "logs a 30m walk with 100m elevation", "behaviour": "straight"},
    {"persona": "confused", "intent": "says random greetings without logging anything", "behaviour": "non-answer"},
    {"persona": "precise", "intent": "logs 150g chicken breast and 200g broccoli", "behaviour": "straight"},
    {"persona": "chatty", "intent": "logs a piece of cake but also talks about the party", "behaviour": "multi-intent"},
    {"persona": "vague", "intent": "I ate some pasta", "behaviour": "non-answer"},
    {"persona": "metric-focused", "intent": "logs current weight as 75.5kg", "behaviour": "straight"},
    {"persona": "indecisive", "intent": "wants to log pizza, then changes mind to salad", "behaviour": "contradiction"},
    {"persona": "demanding", "intent": "how many calories do I have left today?", "behaviour": "straight"}
]

@pytest.mark.asyncio
@pytest.mark.live
@pytest.mark.parametrize("config", SCENARIOS_DATA, ids=[c["persona"] for c in SCENARIOS_DATA])
async def test_qa_batch(config, db_session, run, settings):
    from harness.state import create_onboarded_user
    from calobot.persistence.seed import seed_all
    
    await seed_all(db_session)
    user = await create_onboarded_user(db_session, 42)
    now = dt.datetime.now(settings.timezone)
    
    persona = Persona(name=config["persona"], description=f"A user with persona: {config['persona']}", repertoire=())
    step = Step(intent=config["intent"], expect=NothingStored(), behaviour=config.get("behaviour", "straight"))
    
    scenario = Scenario(
        name="qa-test-" + config["persona"],
        persona=persona,
        starts_at=now,
        steps=[step],
        action_cap=15,
    )
    
    sim_user = SimulatedUser(LLMGateway(settings), persona)
    
    try:
        report = await run_scenario(
            scenario,
            run=run,
            user=sim_user,
            session=db_session,
            user_id=user.id,
            tz=settings.timezone,
        )
        out = report.__dict__
        out["qa_scenario"] = config
        out["verdicts"] = [v.__dict__ for v in out.get("verdicts", [])]
        out["failures"] = [f.__dict__ for f in out.get("failures", [])]
        
        with open(f".gemini/tmp/qa-{config['persona']}.json", "w") as f:
            def default(obj):
                try: return str(obj)
                except: return None
            json.dump(out, f, default=default)
            
    except Exception as e:
        with open(f".gemini/tmp/qa-{config['persona']}.json", "w") as f:
            json.dump({"error": str(e), "qa_scenario": config}, f)
