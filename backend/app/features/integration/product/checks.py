"""Deterministic browser evidence checks for B; never creates persona outcomes."""
EXPECTED_ROWS = [['Apples', '2', '1.25'], ['Oranges', '3', '2.00']]

# Read rendered text/state, not an application's hidden output object.
OBSERVE_SCRIPT = """() => ({
  verdict: document.querySelector('#verdict')?.textContent || '',
  rows: [...document.querySelectorAll('#table tbody tr')].map(row =>
    [...row.querySelectorAll('td button')].map(cell => cell.textContent)),
  selected: (() => { const cell = document.querySelector('td.selected');
    return cell ? {row: Number(cell.dataset.row), column: Number(cell.dataset.column),
                   text: cell.textContent} : null; })(),
  source_detail: document.querySelector('#source-detail')?.textContent || '',
  error_count: document.querySelectorAll('#errors .error-item').length
})"""


def evaluate(check_id, observation):
    """A true check alone is not a saved trial; B must retain actual action evidence."""
    if observation.get('rows') != EXPECTED_ROWS:
        return False
    selected = observation.get('selected')
    if check_id == 'sourcetable-normal-v1':
        return (observation.get('verdict') == 'Schema checks passed'
                and observation.get('error_count') == 0
                and selected == {'row': 2, 'column': 2, 'text': '2'}
                and 'Page 1' in observation.get('source_detail', ''))
    if check_id == 'sourcetable-type-error-v1':
        return (observation.get('verdict') == 'Schema errors found'
                and observation.get('error_count', 0) >= 1
                and selected == {'row': 2, 'column': 1, 'text': 'Apples'}
                and 'Page 1' in observation.get('source_detail', ''))
    if check_id == 'sourcetable-recovery-v1':
        return observation.get('verdict') == 'Schema checks passed' and observation.get('error_count') == 0
    return False
