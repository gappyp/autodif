#!/usr/bin/env python2.7

"""
* TODO: AML need needs to confirm mapping and hz calculation
"""

from __future__ import print_function

import os
import datetime
import re
import sys
from itertools import islice
from pprint import pprint
import argparse

from orderedattrdict import AttrDict as OrdAttrDict

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
parser = argparse.ArgumentParser(description='convert Autodif observations file to extract.bat/run.bat file')

parser.add_argument('in_fn', action="store", help='autodif input file', type=str)
parser.add_argument('-o', dest='out_fn', action="store", help='output to this file (won\'t print to stdout)', type=str)

parser.add_argument('--np', action="store_true", default=False, help='don\'t include PPM readings')
parser.add_argument('--mro', action="store_true", default=False, help='only include obs that have mark readings')

# if first obs doesn't have mark reading, supply them here
parser.add_argument('--mu', action="store", type=str, help='will set the first missing mu reading to this (decimal degrees or dd,mm,ss.ss)')
parser.add_argument('--md', action="store", type=str, help='will set the first missing md reading to this (decimal degrees or dd,mm,ss.ss)')

args = parser.parse_args()

#print(args)
#sys.exit()

# ----------------------------------------------------------------------------------------------------------------------
ad_toks =      ['RecTime', 'LaserPU',  'LaserPD',  'Decl1UE', 'Decl2DW', 'Decl3DE', 'Decl4UW', 'LaserPU',  'LaserPD',  'Incl1US', 'Incl2DN', 'Incl3DS', 'Incl4UN']
ga_toks =      [None,      'mu',       'md',       'nu',      'nd',      'sd',      'su',      'mu',       'md',       'eu',      'ed',      'wd',      'wu'     ]
ad_toks_uniq = ['RecTime', 'LaserPU1', 'LaserPD1', 'Decl1UE', 'Decl2DW', 'Decl3DE', 'Decl4UW', 'LaserPU2', 'LaserPD2', 'Incl1US', 'Incl2DN', 'Incl3DS', 'Incl4UN']      # these are the same except for unique mark readings
ga_toks_uniq = [None,      'mu1',      'md1',      'nu',      'nd',      'sd',      'su',      'mu2',      'md2',      'eu',      'ed',      'wd',      'wu'     ]

# even more stuff for indexing
exec((', '.join(ad_toks_uniq))+' = range(len(ad_toks_uniq))')
ga_toks_uniq_nn = list(ga_toks_uniq); ga_toks_uniq_nn.remove(None)
exec((', '.join(ga_toks_uniq_nn))+' = range(1, len(ga_toks_uniq_nn)+1)')

tok_map = dict(zip(ad_toks, ga_toks))

# use regex to get valid lines and extract data
p0 = '|'.join(key for key in tok_map.keys() if key != 'RecTime')
p1 = r'((?P<ad_tok>{})\s+(?P<date>\d{{4}}-\d{{2}}-\d{{2}})\s+(?P<time>\d{{2}}:\d{{2}}:\d{{2}})\s+(?P<value>\d{{3}}\.\d*)\s*)'.format(p0)
p2 = r'((?P<ad_tok>{})\s+(?P<date>\d{{4}}-\d{{2}}-\d{{2}})\s+(?P<time>\d{{2}}:\d{{2}}:\d{{2}})\s+(?P<value>(COMPLETE|MAGNETIC))\s*)'.format('RecTime')

obs = []
with open(args.in_fn, 'r') as fp:
    for ln, line in enumerate(fp):
        m_p1 = re.search(p1, line)
        if m_p1:
            ob = AttrDict(m_p1.groupdict())
            ob.value = float(ob.value)
        else:
            m_p2 = re.search(p2, line)
            if m_p2:
                ob = AttrDict(m_p2.groupdict())
                #if ob.value == 'MAGNETIC':
                #    ob.value = None                 # TODO: might be more readable to leave this as MAGNETIC
            else:
                continue
        ob.ga_tok = tok_map[ob.ad_tok]
        ob.dt = datetime.datetime.strptime(ob.date+'T'+ob.time, "%Y-%m-%dT%H:%M:%S")
        ob.fn = args.in_fn      # TODO: so frustrating not having pathlib... this will need to use cwd when relative path
        ob.ln = ln
        obs.append(ob)

# TODO: this won't be true now that include rectime token. need to split the list and assert order
#assert obs == sorted(obs, key=lambda ob: ob.dt)

# ----------------------------------------------------------------------------------------------------------------------
wmr_obs = []        # with mark reading
for ob in window(obs, len(ad_toks)):
    if [x.ad_tok for x in ob] == ad_toks:

        wmr_obs.append(AttrDict({'comment':'# source: {}:{}:{}'.format(ob[0].fn, ob[0].ln, ob[-1].ln), 'ob':ob}))       # TODO: maybe put line numbers in source file
# sort by first mu datetime, just incase
wmr_obs = sorted(wmr_obs, key=lambda abs_ob: abs_ob.ob[LaserPU1].dt)       # TODO: untested

sys.exit()

# **********************************************************************************************************************
nmr_toks = ['RecTime', 'Decl1UE', 'Decl2DW', 'Decl3DE', 'Decl4UW', 'Incl1US', 'Incl2DN', 'Incl3DS', 'Incl4UN']
nmr_obs = []        # no mark reading
for ob in window(obs, len(nmr_toks)):
    if [x.ad_tok for x in ob] == nmr_toks:
        nmr_obs.append(ob)
# sort by Decl1UE datetime, just incase
wmr_obs = sorted(wmr_obs, key=lambda abs_ob: abs_ob.ob[1].dt)               # TODO: untested

# ----------------------------------------------------------------------------------------------------------------------
if args.mro:
    abs_obs = wmr_obs       # easy
else:
    # can make complicated here, for now just use last mark-reading
    if args.mu:
        pass

for obs in abs_obs:
    pprint(obs)
    print('-'*80)

sys.exit()

# group obs to get a list of ga 'Begin Absolute'
#abs_obs = []

# ======================================================================================================================
# TODO: think creates a new string each time '+='... confirm this and if the case maybe '\n'.join(append-to-a-list)
# for each abs obs create a string
def get_abs_ob_str(abs_ob):
    by_adu = AttrDict(zip(ad_toks_uniq, abs_ob))
    by_gau = AttrDict(zip(ga_toks_uniq, abs_ob))

    abs_ob_str =  'Begin Absolutes {date:} {time:} CNB #VAR#\n'.format(date=by_gau.mu1.dt.strftime('%Y/%m/%d'), time=by_gau.mu1.dt.strftime('%H:%M'))
    abs_ob_str += 'Begin DIM {date:} CNB gsb N Cw AUTODIF_007E AUTODIF_007\n'.format(date=by_gau.mu1.dt.strftime('%Y/%m/%d'))
    abs_ob_str += 'mu  {:03.0f} {:02.0f}\'{:02.0f}"\n'.format(*dd2dms(float(by_gau.mu1.value)))
    abs_ob_str += 'md  {:03.0f} {:02.0f}\'{:02.0f}"\n'.format(*dd2dms(float(by_gau.md1.value)))
    # declination obs
    for ob in abs_ob[Decl1UE:Decl4UW+1]:
        d, m, s = dd2dms(float(ob.value))
        abs_ob_str += '{ga_tok:} {time:} {d:03.0f} {m:02.0f}\'{s:02.0f}"     ; T +000.0:\n'.format(ga_tok=ob.ga_tok, time=ob.time, d=d, m=m, s=s)
    # 2nd lot of mark readings
    abs_ob_str += 'mu  {:03.0f} {:02.0f}\'{:02.0f}"\n'.format(*dd2dms(float(by_gau.mu2.value)))
    abs_ob_str += 'md  {:03.0f} {:02.0f}\'{:02.0f}"\n'.format(*dd2dms(float(by_gau.md2.value)))

    # calculate hz1 and hz2. should be in the half of north?     # TODO: needs confirmation
    hz_calc_angs = [float(ob.value) for ob in abs_ob[Decl1UE:Decl4UW+1]]
    hz1 = mean([x%180.0 for x in hz_calc_angs])
    #hz1 += 180.0
    if hz_calc_angs[0] <= 180:
        pass
    else:
        hz1 += 180.0        # to bring into the 2nd half
    hz1 = (hz1+90.0)%360
    hz2 = (hz1+180.0)%360.0

    abs_ob_str += 'hz       {:03.0f} {:02.0f}\'{:02.0f}"\n'.format(*dd2dms(hz1))
    # inclination obs
    for ob in abs_ob[Incl1US:Incl2DN+1]:
        d, m, s = dd2dms(float(ob.value))
        abs_ob_str += '{ga_tok:} {time:} {d:03.0f} {m:02.0f}\'{s:02.0f}"     ; T +000.0:\n'.format(ga_tok=ob.ga_tok, time=ob.time, d=d, m=m, s=s)
    abs_ob_str += 'hz       {:03.0f} {:02.0f}\'{:02.0f}"\n'.format(*dd2dms(hz2))
    for ob in abs_ob[Incl3DS:Incl4UN+1]:
        d, m, s = dd2dms(float(ob.value))
        abs_ob_str += '{ga_tok:} {time:} {d:03.0f} {m:02.0f}\'{s:02.0f}"     ; T +000.0:\n'.format(ga_tok=ob.ga_tok, time=ob.time, d=d, m=m, s=s)
    abs_ob_str += 'End DIM\n'
    abs_ob_str += 'End Absolutes\n'

    return abs_ob_str

# ======================================================================================================================
if args.out_fn:
    fp = open(args.out_fn, 'w')
else:
    fp = sys.stdout

for abs_ob in abs_obs:
    print(get_abs_ob_str(abs_ob), file=fp)

if args.out_fn:
    fp.close()