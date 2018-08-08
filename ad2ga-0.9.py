#!/usr/bin/env python2.7

"""
* TODO: if obs goes over UT day need to do the 24:xx:xx thing
* TODO: could put in 3 lots of mark readings if want and if run.bat accepts this
"""

import os
import datetime
import re
import sys
from itertools import islice
from pprint import pprint

# ======================================================================================================================
# TODO: these classes and function mainly from internet. need to double check

class AttrDict(dict):
    def __init__(self, *args, **kwargs):
        super(AttrDict, self).__init__(*args, **kwargs)
        self.__dict__ = self

# ----------------------------------------------------------------------------------------------------------------------
def dd2dms(dd):
   is_positive = dd >= 0
   dd = abs(dd)
   minutes,seconds = divmod(dd*3600,60)
   degrees,minutes = divmod(minutes,60)
   degrees = degrees if is_positive else -degrees
   return (degrees,minutes,seconds)

# ----------------------------------------------------------------------------------------------------------------------
# takes floats, uses sign of degrees
def dms2dd(d, m, s):
    if d < 0:
        return d-m/60-s/(60*60)
    else:
        return d+m/60+s/(60*60)

# ----------------------------------------------------------------------------------------------------------------------
# from https://stackoverflow.com/questions/6822725/rolling-or-sliding-window-iterator
def window(seq, n=2):
    "Returns a sliding window (of width n) over data from the iterable"
    "   s -> (s0,s1,...s[n-1]), (s1,s2,...,sn), ...                   "
    it = iter(seq)
    result = tuple(islice(it, n))
    if len(result) == n:
        yield result
    for elem in it:
        result = result[1:] + (elem,)
        yield result

# python3 has statistics.mean :'(
# from https://stackoverflow.com/questions/7716331/calculating-arithmetic-mean-one-type-of-average-in-python
def mean(numbers):
    return float(sum(numbers)) / max(len(numbers), 1)

# ======================================================================================================================
in_fn = '/nas/users/u43382/unix/autodif/20180807.abs'

# pathname needs modifying based on date... leave like this for now
out_fn = os.path.splitext(in_fn)[0]+'.obs'
#print out_fn

ad_toks = ['LaserPU', 'LaserPD', 'Decl1UE', 'Decl2DW', 'Decl3DE', 'Decl4UW', 'LaserPU', 'LaserPD', 'Incl1US', 'Incl2DN', 'Incl3DS', 'Incl4UN']
ga_toks = ['mu',      'md',      'nu',      'nd',      'sd',      'su',      'mu',      'md',      'eu',      'ed',      'wd',      'wu'     ]

# below changed strings for lasers, so that unique
ad_toks_uniq = ['LaserPU1', 'LaserPD1', 'Decl1UE', 'Decl2DW', 'Decl3DE', 'Decl4UW', 'LaserPU2', 'LaserPD2', 'Incl1US', 'Incl2DN', 'Incl3DS', 'Incl4UN']
ga_toks_uniq = ['mu1',      'md1',      'nu',      'nd',      'sd',      'su',      'mu2',      'md2',      'eu',      'ed',      'wd',      'wu'     ]

# even more stuff for indexing
exec((', '.join(ad_toks_uniq))+' = range(len(ad_toks_uniq))')
exec((', '.join(ga_toks_uniq))+' = range(len(ga_toks_uniq))')

tok_map = dict(zip(ad_toks, ga_toks))             # token mapping. don't care about RecTime?
#print tok_map
#sys.exit()

# use regex to get valid lines
ad_tok_pat = '|'.join(tok_map.keys())         # autodif token pattern
#print ad_tok_pat

pat = r'((?P<ad_tok>{})\s+(?P<date>\d{{4}}-\d{{2}}-\d{{2}})\s+(?P<time>\d{{2}}:\d{{2}}:\d{{2}})\s+(?P<value>\d{{3}}\.\d*)\s*)'.format(ad_tok_pat)
#pat = r'({})'.format(ad_tok_pat)
#print(pat)

with open(in_fn, 'r') as fp:
    in_str = fp.read()

obs = []
matches = re.finditer(pat, in_str)
for match in matches:
    ob = AttrDict(match.groupdict())
    ob.ga_tok = tok_map[ob.ad_tok]
    ob.dt = datetime.datetime.strptime(ob.date+'T'+ob.time, "%Y-%m-%dT%H:%M:%S")

    obs.append(ob)

# assert in time order          # TODO: unchecked
assert obs == sorted(obs, key=lambda ob: ob.dt)

# group obs to get a list of ga 'Begin Absolute'
abs_obs = []
for g_num, abs_ob in enumerate(window(obs, len(ad_toks))):
    if [x.ad_tok for x in abs_ob] == ad_toks:
        abs_obs.append(abs_ob)
        # could also put time constraints for an observation here...

#pprint(abs_obs)

# ======================================================================================================================
# for each abs obs create a string
def get_abs_ob_str(abs_ob):
    by_adu = AttrDict(zip(ad_toks_uniq, abs_ob))
    by_gau = AttrDict(zip(ga_toks_uniq, abs_ob))

    abs_ob_str =  'Begin Absolutes {date:} {time:} CNB #VAR#\n'.format(date=by_gau.mu1.dt.strftime('%Y/%m/%d'), time=by_gau.mu1.dt.strftime('%H:%M'))
    abs_ob_str += 'Begin DIM {date:} CNB gsb N Cw AUTODIF007E AUTODIF007\n'.format(date=by_gau.mu1.dt.strftime('%Y/%m/%d'))
    abs_ob_str += 'mu  {:03.0f} {:02.0f}\'{:02.0f}"\n'.format(*dd2dms(float(by_gau.mu1.value)))
    abs_ob_str += 'md  {:03.0f} {:02.0f}\'{:02.0f}"\n'.format(*dd2dms(float(by_gau.md1.value)))
    # declination obs
    for ob in abs_ob[Decl1UE:Decl4UW+1]:
        d, m, s = dd2dms(float(ob.value))
        abs_ob_str += '{ga_tok:} {time:} {d:03.0f} {m:02.0f}\'{s:02.0f}     ; T +000.0"\n'.format(ga_tok=ob.ga_tok, time=ob.time, d=d, m=m, s=s)
    # 2nd lot of mark readings
    abs_ob_str += 'mu  {:03.0f} {:02.0f}\'{:02.0f}"\n'.format(*dd2dms(float(by_gau.mu2.value)))
    abs_ob_str += 'md  {:03.0f} {:02.0f}\'{:02.0f}"\n'.format(*dd2dms(float(by_gau.md2.value)))

    # calculate hz1 and hz2. should be in the half of north?     # TODO: needs confirmation
    hz_calc_angs = [float(ob.value) for ob in abs_ob[Decl1UE:Decl4UW+1]]
    hz1 = mean([x%180.0 for x in hz_calc_angs])
    if hz_calc_angs[0] <= 180:
        pass
    else:
        hz1 += 180.0        # to bring into the 2nd half
    hz2 = (hz1+180.0)%360.0

    abs_ob_str += 'hz       {:03.0f} {:02.0f}\'{:02.0f}"\n'.format(*dd2dms(hz1))
    # inclination obs
    for ob in abs_ob[Incl1US:Incl2DN+1]:
        d, m, s = dd2dms(float(ob.value))
        abs_ob_str += '{ga_tok:} {time:} {d:03.0f} {m:02.0f}\'{s:02.0f}     ; T +000.0"\n'.format(ga_tok=ob.ga_tok, time=ob.time, d=d, m=m, s=s)
    abs_ob_str += 'hz       {:03.0f} {:02.0f}\'{:02.0f}"\n'.format(*dd2dms(hz2))
    for ob in abs_ob[Incl3DS:Incl4UN+1]:
        d, m, s = dd2dms(float(ob.value))
        abs_ob_str += '{ga_tok:} {time:} {d:03.0f} {m:02.0f}\'{s:02.0f}     ; T +000.0"\n'.format(ga_tok=ob.ga_tok, time=ob.time, d=d, m=m, s=s)
    abs_ob_str += 'End DIM\n'
    abs_ob_str += 'End Absolutes\n'

    return abs_ob_str

for abs_ob in abs_obs:
    print(get_abs_ob_str(abs_ob))
