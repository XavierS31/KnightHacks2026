"""Three bounded SourceTable v1 UI improvements, written as implementer edits.

These came from reading the v1 interface, not from executed persona feedback. To patch
the product, each one must match a supported E1 proposal with session evidence, and a
human must review its scope. Each touches only `product/ui/app.js` and keeps every element
id, data attribute and verdict text that the fixed checks observe.
"""

from backend.app.features.evolution.models import BoundedEdit
from backend.app.shared.contracts import Contract

APP_JS = "product/ui/app.js"
RERUN_STATUS = "Inputs changed. Run Extract & validate again to see current results."
BUSY_LABEL = "Extracting…"


class BoundedImprovement(Contract):
    key: str
    title: str
    problem: str
    change: str
    acceptance_check: str
    allowed_paths: list[str]
    edits: list[BoundedEdit]


STALE_STATUS = BoundedImprovement(
    key="stale-status-after-input-change",
    title="Say when a shown result is out of date",
    problem="Changing a column rule hides the result, but the status still says the check is "
            "complete.",
    change="When inputs change after a result, the status asks the user to run the check again.",
    acceptance_check=f"After a completed check, changing a column type hides the result and the "
                     f"status reads '{RERUN_STATUS}'",
    allowed_paths=[APP_JS],
    edits=[BoundedEdit(
        path=APP_JS, find="function clearResult(){result=null;",
        replace=f"function clearResult(){{if(result)$('status').textContent='{RERUN_STATUS}';"
                "result=null;")],
)

FIRST_ERROR = BoundedImprovement(
    key="inspect-first-error",
    title="Show the source of the first error at once",
    problem="After a failed check, the source panel stays empty until the user finds and "
            "selects an error.",
    change="An invalid result selects the first error's source cell automatically.",
    acceptance_check="After an Item integer check, without another action, row 2 column 1 "
                     "('Apples') is selected and the source panel names page 1",
    allowed_paths=[APP_JS],
    edits=[BoundedEdit(
        path=APP_JS,
        find="$('source-detail').textContent='Select a data cell or validation error.';"
             "mapCells(null);",
        replace="$('source-detail').textContent='Select a data cell or validation error.';"
                "mapCells(null);const firstError=result.errors.find(error=>error.source_cell);"
                "if(firstError)selectCell(firstError.source_cell);")],
)

BUSY_BUTTON = BoundedImprovement(
    key="busy-extract-button",
    title="Show progress on the Extract button",
    problem="While a check runs, the disabled button keeps its idle label; only small status "
            "text shows progress.",
    change="During a check the button reads 'Extracting…' and is marked busy; it resets after.",
    acceptance_check=f"While a check runs, the Extract button reads '{BUSY_LABEL}' with "
                     f"aria-busy=true; afterwards it reads 'Extract & validate' without aria-busy",
    allowed_paths=[APP_JS],
    edits=[
        BoundedEdit(
            path=APP_JS, find="$('status').textContent='Extracting and checking your table…';",
            replace="$('status').textContent='Extracting and checking your table…';"
                    f"$('execute').textContent='{BUSY_LABEL}';"
                    "$('execute').setAttribute('aria-busy','true');"),
        BoundedEdit(
            path=APP_JS, find="finally{busy=false;ready();}};\n$('download')",
            replace="finally{busy=false;$('execute').textContent='Extract & validate';"
                    "$('execute').removeAttribute('aria-busy');ready();}};\n$('download')"),
    ],
)

BOUNDED_IMPROVEMENTS = [STALE_STATUS, FIRST_ERROR, BUSY_BUTTON]
