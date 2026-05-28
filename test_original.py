"""Test /original page directly."""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Init Firebase
from backend.firebase_init import init_admin_sdk
try:
    init_admin_sdk()
except Exception:
    pass

# Mimic what /original does
from server.routes.pages import _load_curriculum_subjects
from server.services.engine import get_engine

print("=== Test 1: _load_curriculum_subjects ===")
try:
    curr = _load_curriculum_subjects()
    print(f"OK: {len(curr)} curriculums")
except Exception as e:
    import traceback
    print(f"FAIL: {e}")
    traceback.print_exc()

print("\n=== Test 2: engine.get_unique_years ===")
try:
    engine = get_engine()
    years = engine.get_unique_years()
    print(f"OK: {len(years) if years else 0} years, sample: {list(years)[:5] if years else []}")
except Exception as e:
    import traceback
    print(f"FAIL: {e}")
    traceback.print_exc()

print("\n=== Test 3: template rendering ===")
try:
    from server import config
    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory=str(config.TEMPLATES_DIR))
    
    # Get the template
    template = templates.get_template("original_exam.html")
    print(f"OK: template loaded")
    
    # Try to render it
    rendered = template.render(
        request=None,
        user={"uid": "test"},
        sources=[],
        curriculums=curr if 'curr' in dir() else {},
        curriculum_names=[],
        all_years=years if 'years' in dir() else [],
    )
    print(f"OK: rendered ({len(rendered)} chars)")
except Exception as e:
    import traceback
    print(f"FAIL: {e}")
    traceback.print_exc()

