"""Regression for the blank direct-entry form in Rajan Dental v0.2.

Checks both form components define every queue state read during render.
"""
from pathlib import Path
import re

source=Path(__file__).resolve().parents[1]/'src'/'AdvancedUI.jsx'
code=source.read_text()
for component in ('EstimateEditor','InvoiceEditor'):
    start=code.index('function '+component+'(')
    end=code.find('\nfunction ',start+1)
    if end == -1:
        end=code.find('\nexport function ',start+1)
    body=code[start:end if end!=-1 else None]
    assert '[queued,setQueued]=useState([])' in body, f'{component}: missing queue state causes a blank drawer'
    assert 'queued.map(' in body, f'{component}: direct procedure queue not rendered'
    assert 'setQueued(' in body, f'{component}: cannot add multiple procedures'
assert code.count('setLine(current=>{const tariff=procs.find') >= 2
print('PASS: estimate + invoice direct-procedure render state and tariff updates')
