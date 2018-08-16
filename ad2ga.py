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
from os.path import join
import glob
import subprocess
import time

if 'win' in sys.platform:
    root_d = r'\\prod.lan\active\ops'
    env = {'Path':join(root_d, 'AusGN', 'gm', 'w')}
    temp_d = os.environ['TEMP']
elif 'lin' in sys.platform:
    root_d = r'/nas/active/ops'
    env = {'PATH':'/opt/gm'}
    temp_d = '/tmp'

assert os.path.isdir(temp_d)
# TODO: should assert other dirs?

cnb_d = join(root_d, 'AusGN', 'gm', 'obs', 'cnb')

from orderedattrdict import AttrDict as OrdAttrDict
#from attrdict import AttrDict
from collections import defaultdict

# the borrowed AttrDict is shit
class AttrDict(dict):
    def __init__(self, *args, **kwargs):
        super(AttrDict, self).__init__(*args, **kwargs)
        self.__dict__ = self

# ======================================================================================================================
# TODO: these mainly from internet. need to double check
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
# this needed because str format second rounding produces angles with 60 seconds... and will likely produce similar for minutes, degrees etc
def dd2dms_shim(dd):
    d, m, s = dd2dms(float(dd))
    s_str = '{:02.0f}'.format(s)
    if s_str == '60':
        s_str = '00'
        m += 1
    m_str = '{:02.0f}'.format(m)
    if m_str == '60':
        m_str = '00'
        d += 1

    d = d%360.0
    d_str = '{:03.0f}'.format(d)
    return '{} {}\'{}"'.format(d_str,m_str,s_str)
# TESTS HERE
#print(dd2dms_shim(044.9666))
#print(dd2dms_shim(359.9999))
#sys.exit()

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
g1 = parser.add_mutually_exclusive_group()

parser.add_argument('in_fn', action="store", help='autodif input file', type=str)
parser.add_argument('-o', dest='out_fn', action="store", help='output to this file (won\'t print to stdout)', type=str)

parser.add_argument('--np', action="store_true", default=False, help='[NOT YET IMPLEMENTED] don\'t include PPM readings')
g1.add_argument('--mro', action="store_true", default=False, help='only include obs that have mark readings')

# if first obs doesn't have mark reading, supply them here
# TODO: make it so requires both :S???
g1.add_argument('--mud', action="store", type=str, help="force the first missing mark up and down readings. e.g. 'u180d1' or 'u180' (d will be calculated to be 0) or 'd180,0,1.1u0.0' (d is in dms)")

args = parser.parse_args()

if args.mud != None:
    map = {'u':'d', 'd':'u'}
    first = args.mud[0]
    assert first in map.keys()
    second = {'u':'d', 'd':'u'}[first]
    fs = args.mud[1:].split(second)
    temp = []
    for ang_str in fs:
        dms = ang_str.split(',')
        total = 0
        for part, mult in zip(dms, [1.0, 1.0/60.0, 1.0/(60.0*60.0)]):
            total += float(part)*mult
        temp.append(total)
    if len(temp) == 1:
        temp.append((temp[0]+180.0)%360.0)
    assert len(temp) == 2
    if first == 'u':
        args.mud = temp
    else:
        args.mud = list(reversed(temp))
    #print(args.mud)

# ----------------------------------------------------------------------------------------------------------------------
ad_toks =      ['RecTime', 'LaserPU',  'LaserPD',  'Decl1UE', 'Decl2DW', 'Decl3DE', 'Decl4UW', 'LaserPU',  'LaserPD',  'Incl1US', 'Incl2DN', 'Incl3DS', 'Incl4UN']
ga_toks =      [None,      'mu',       'md',       'nu',      'nd',      'sd',      'su',      'mu',       'md',       'eu',      'ed',      'wd',      'wu'     ]

for ref in ['ad_toks', 'ga_toks']:
    exec('toks = {}'.format(ref))
    occs = defaultdict(int)        # occurences
    for tok in toks:
        occs[tok] += 1
    suff_cntr = {tok:1 for tok, occ in occs.items() if occ > 1}     # suffix counter
    suff_toks = []
    for tok in toks:
        if tok in suff_cntr:
            suff_toks.append(tok+str(suff_cntr[tok]))
            suff_cntr[tok] += 1
        else:
            suff_toks.append(tok)
    exec('{}_uniq = suff_toks'.format(ref))

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
        by_adu = OrdAttrDict(zip(ad_toks_uniq, ob))
        by_gau = OrdAttrDict(zip(ga_toks_uniq, ob))
        wmr_obs.append(AttrDict({'comment':'# source: {}:{}:{}\n'.format(ob[0].fn, ob[0].ln, ob[-1].ln),
                                 'mr_comment':'# mu: {}:{}\n# md: {}:{}\n'.format(ob[0].fn, by_gau.mu2.ln, ob[0].fn, by_gau.md2.ln),
                                 'dt':by_adu.LaserPU1.dt,
                                 'by_adu':by_adu,
                                 'by_gau':by_gau}))
# sort by first mu datetime, just incase
wmr_obs.sort(key=lambda abs_ob: abs_ob.by_gau.mu1.dt)       # TODO: untested

# **********************************************************************************************************************
# TODO: this is really gross, needs changing
# TODO: also has hardcoded mu and md in... won't work if change mapping (though this won't happen)
def ga_tok_select(tok):
    if tok is None:
        return True
    elif 'mu' in tok:
        return False
    elif 'md' in tok:
        return False
    else:
        return True
nmr_ad_toks      = [tok for tok in ad_toks      if 'Laser' not in tok]
#nmr_ad_toks_uniq = [tok for tok in ad_toks_uniq if 'Laser' not in tok]
nmr_ga_toks      = [tok for tok in ga_toks      if ga_tok_select(tok)]
#nmr_ga_toks_uniq = [tok for tok in ga_toks_uniq if ga_tok_select(tok)]
# nmr_... and nmr_..._uniq should be the same. wat the hell am i doing :S
assert len(nmr_ad_toks) == len(nmr_ga_toks)

nmr_obs = []        # no mark reading
for ob in window(obs, len(nmr_ad_toks)):
    if [x.ad_tok for x in ob] == nmr_ad_toks:
        by_adu = OrdAttrDict(zip(nmr_ad_toks, ob))
        by_gau = OrdAttrDict(zip(nmr_ga_toks, ob))
        nmr_obs.append(AttrDict({'comment':'# source: {}:{}:{}\n'.format(ob[0].fn, ob[0].ln, ob[-1].ln),
                                 'dt':by_gau.nu.dt,
                                 'by_adu':by_adu,
                                 'by_gau':by_gau}))
# sort by Decl1UE datetime, just incase
#nmr_obs = sorted(nmr_obs, key=lambda abs_ob: abs_ob.by_gau.mu1.dt)               # this won't work because doesn't have that :D... that is good
nmr_obs.sort(key=lambda abs_ob: abs_ob.by_gau.nu.dt)               # this won't work because doesn't have that :D... that is good

# ----------------------------------------------------------------------------------------------------------------------
if args.mro:
    abs_obs = wmr_obs       # easy
else:
    # can make complicated here, for now just use last mark-reading
    if args.mud != None:
        mu, md = args.mud
        nmr_obs[0].by_gau.mu1 = nmr_obs[0].by_adu.LaserPU1 = AttrDict([('value', mu), ('dt', nmr_obs[0].by_gau.nu.dt)])
        nmr_obs[0].by_gau.mu2 = nmr_obs[0].by_adu.LaserPU1 = AttrDict([('value', mu), ('dt', nmr_obs[0].by_gau.nu.dt)])
        nmr_obs[0].by_gau.md1 = nmr_obs[0].by_adu.LaserPD2 = AttrDict([('value', md), ('dt', nmr_obs[0].by_gau.eu.dt)])
        nmr_obs[0].by_gau.md2 = nmr_obs[0].by_adu.LaserPD2 = AttrDict([('value', md), ('dt', nmr_obs[0].by_gau.eu.dt)])
        # first has now been set if given at command line
        # merge into wmr obs
        forced_obs = nmr_obs.pop(0)
        forced_obs.mr_comment = '# mu: forced\n# md: forced\n'
        forced_obs.comment += forced_obs.mr_comment
        wmr_obs.append(forced_obs)
        wmr_obs.sort(key=lambda abs_ob: abs_ob.by_gau.mu1.dt)

    # for each no-mark-reading obs, determine from those with mark readings
    for nmr_ob in nmr_obs:
        # get observations with less than times
        pot_obs = [abs_ob for abs_ob in wmr_obs if abs_ob.by_gau.mu2.dt <= nmr_ob.dt]
        pot_obs.sort(key=lambda abs_ob: abs_ob.by_gau.mu2.dt)
        nmr_ob.by_gau.mu1 = nmr_ob.by_gau.mu2 = pot_obs[-1].by_gau.mu2
        nmr_ob.by_gau.md1 = nmr_ob.by_gau.md2 = pot_obs[-1].by_gau.md2
        nmr_ob.comment += pot_obs[-1].mr_comment

    abs_obs = wmr_obs+nmr_obs
    abs_obs.sort(key=lambda abs_ob: abs_ob.dt)

# ======================================================================================================================
r'((?P<ad_tok>{})\s+(?P<date>\d{{4}}-\d{{2}}-\d{{2}})\s+(?P<time>\d{{2}}:\d{{2}}:\d{{2}})\s+(?P<value>\d{{3}}\.\d*)\s*)'.format(p0)
p3 = r'(\d{2}:\d{2}:\d{1,2}.?\d*)\s+F\s+(\d+.*\d*)'
# now have all the information we need from .abs file, now get PPM data if needed
if args.np:
    # no ppm (i.e. don't want it)
    for abs_ob in abs_obs:
        abs_ob.ppm_str = None
else:
    # want ppm
    file_date = abs_obs[0].dt.date()
    pathname = join(cnb_d, str(file_date.year), 'rawhdata', 'h{}*.cnb'.format(file_date.strftime('%y%j')))

    fns = glob.glob(pathname)
    # TODO: deal with sequence changes
    if len(fns) == 0:
        # no day files
        for abs_ob in abs_obs:      # TODO: this is duplicated. make a function
            abs_ob.ppm_str = None
    else:
        machview_output = []
        for fn in fns:
            # create a temporary file
            temp_fn = join(temp_d, 'ad2ga.{}.{}.txt'.format(os.getpid(), time.time()))
            assert not os.path.isfile(temp_fn)

            sh_fmt = r'\"{}\"'
            sh_fn = sh_fmt.format(fn)
            sh_temp_fn = sh_fmt.format(temp_fn)

            cmd_date_str = file_date.strftime('%Y/%m/%d')
            #cmd = r'machview /Select=F /FRom=\"2018/08/08T10:00:00.0\" /To=\"2018/08/08T23:59:59.9\" /Out={} {}'.format(sh_temp_fn, sh_fn)
            cmd = r'machview /Select=F /FRom=\"{}T00:00:00.0\" /To=\"{}T23:59:59.9\" /Out={} {}'.format(cmd_date_str, cmd_date_str, sh_temp_fn, sh_fn)

            PIPE = subprocess.PIPE
            proc = subprocess.Popen(cmd, shell=True, env=env, stdout=PIPE, stderr=PIPE)
            output, err = proc.communicate()
            errcode = proc.returncode
            assert errcode == 0

            with open(temp_fn, 'r') as fp:
                for line in fp:
                    m_p3 = re.search(p3, line)
                    if m_p3:
                        f_time, f_val = m_p3.groups()       # these are strings
                        f_time_h, f_time_m, f_time_s = f_time.split(':')
                        f_time_s, f_time_us = f_time_s.split('.')
                        f_time_us = '{:0<6s}'.format(f_time_us)

                        f_time = datetime.time(int(f_time_h), int(f_time_m), int(f_time_s), int(f_time_us))

                        machview_output.append((datetime.datetime.combine(file_date, f_time), float(f_val)))
            os.remove(temp_fn)      # CAREFUL HERE!!!

        # go through machview_output and look values within tolerance
        # set ppm_str (that will be put b4 anything)
        for abs_ob in abs_obs:
            ul = abs_ob.dt
            ll = ul-datetime.timedelta(minutes=1.0)
            #print(ll, ul)
            ppms = [tpl for tpl in machview_output if ll <= tpl[0] <= ul]
            ppms.sort(key=lambda tpl:tpl[0])    # sort
            ppm_lines = ['Begin PPM {} CNB rmi F GSM90_905926\n'.format(file_date.strftime('%Y/%m/%d'))]
            for dt, val in ppms:
                ppm_lines.append('{:02d}:{:02d}:{:05.2f} {:.2f} :\n'.format(dt.hour, dt.minute, float(dt.second)+float(dt.microsecond)/(10**6), val))
            ppm_lines.append('End PPM\n')
            abs_ob.ppm_str = (''.join(ppm_lines))





# example PPM str
"""
Begin PPM 2018/07/31 CNB aml Aw GSM90_905926 # 21867
03:49:00.0 58010.93 : # a
03:49:10.0 58010.89 : # a
03:49:20.1 58010.92 : # a
03:49:30.0 58010.81 : # a
03:49:40.1 58011.00 : # a
03:49:50.1 58011.03 : # a
03:50:00.0 58011.18 : # a
03:50:10.1 58011.24 : # a
End PPM
"""

#sys.exit()

# ======================================================================================================================
# TODO: think creates a new string each time '+='... confirm this and if the case maybe '\n'.join(append-to-a-list)
# for each abs obs create a string
def get_abs_ob_str(abs_ob):
    by_adu = abs_ob.by_adu
    by_gau = abs_ob.by_gau

    abs_ob_str  = str(abs_ob.comment)
    abs_ob_str += 'Begin Absolutes {date:} {time:} CNB #VAR#\n'.format(date=abs_ob.dt.strftime('%Y/%m/%d'), time=abs_ob.dt.strftime('%H:%M:%S'))
    abs_ob_str += abs_ob.ppm_str
    abs_ob_str += 'Begin DIM {date:} CNB rmi N Cw AUTODIF_007E AUTODIF_007\n'.format(date=by_gau.mu1.dt.strftime('%Y/%m/%d'))
    abs_ob_str += 'mu'+' '*10+'{}\n'.format(dd2dms_shim(float(by_gau.mu1.value)))
    abs_ob_str += 'md'+' '*10+'{}\n'.format(dd2dms_shim(float(by_gau.md1.value)))
    # declination obs
    for ob in ['nu', 'nd', 'sd', 'su']:
        dms_str = dd2dms_shim(float(by_gau[ob].value))
        abs_ob_str += '{ga_tok:} {time:} {dms_str:}     ; T +000.0:\n'.format(ga_tok=ob, time=by_gau[ob].time, dms_str=dms_str)
    # 2nd lot of mark readings
    abs_ob_str += 'mu'+' '*10+'{}\n'.format(dd2dms_shim(float(by_gau.mu2.value)))
    abs_ob_str += 'md'+' '*10+'{}\n'.format(dd2dms_shim(float(by_gau.md2.value)))

    # calculate hz1 and hz2. should be in the half of north?     # TODO: needs confirmation
    hz_calc_angs = [float(by_adu[ob].value) for ob in ['Decl1UE', 'Decl4UW']]
    hz1 = mean([x%180.0 for x in hz_calc_angs])
    #hz1 += 180.0
    if hz_calc_angs[0] <= 180:
        pass
    else:
        hz1 += 180.0        # to bring into the 2nd half
    hz1 = (hz1+90.0)%360
    hz2 = (hz1+180.0)%360.0

    abs_ob_str += 'hz          {}\n'.format(dd2dms_shim(hz1))
    # inclination obs
    for ob in ['eu', 'ed']:
        dms_str = dd2dms_shim(float(by_gau[ob].value))
        abs_ob_str += '{ga_tok:} {time:} {dms_str:}     ; T +000.0:\n'.format(ga_tok=ob, time=by_gau[ob].time, dms_str=dms_str)
    abs_ob_str += 'hz          {}\n'.format(dd2dms_shim(hz2))
    for ob in ['wd', 'wu']:
        dms_str = dd2dms_shim(float(by_gau[ob].value))
        abs_ob_str += '{ga_tok:} {time:} {dms_str:}     ; T +000.0:\n'.format(ga_tok=ob, time=by_gau[ob].time, dms_str=dms_str)
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