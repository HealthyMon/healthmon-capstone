"""Readable aggregation of actual awarded deltas, including clipping."""
from collections import OrderedDict
from .persona_engine import AXES


def summarize_ledger(initial, final, ledger):
    summary = []
    for axis in AXES:
        groups = OrderedDict()
        for row in ledger:
            if row['axis'] != axis:
                continue
            group = groups.setdefault(row['reason_code'], {'reason_code':row['reason_code'],'reason':row['reason'],
                'count':0,'raw_delta':0.,'streak_bonus':0.,'cap_adjustment':0.,'final_delta':0.})
            group['count'] += 1
            for key in ('raw_delta','streak_bonus','cap_adjustment','final_delta'):
                group[key] = round(group[key] + row[key], 8)
        total = round(sum(row['final_delta'] for row in groups.values()), 8)
        if abs(initial[axis] + total - final[axis]) > 1e-6:
            raise ValueError('Ledger does not reconcile with final personality')
        summary.append({'axis':axis,'before':initial[axis],'after':final[axis],'total_delta':total,'reasons':list(groups.values())})
    return summary
