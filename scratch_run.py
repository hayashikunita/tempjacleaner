from tempjacleaner.advanced_rules import run_advanced
from tempjacleaner import check_text

s = 'print("見れる可能性がある")'
print('advanced on block:')
print(list(run_advanced('見れる可能性がある')))
print('check_text advanced:')
print([ (i.message, i.snippet) for i in check_text(s, from_code=True, advanced=True) ])
