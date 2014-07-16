import sqlite3
import time
import os
import re
import gzip
import cStringIO
from sys import platform as _platform
import sys
import sixdeskdir
import lsfqueue
import numpy as np
import matplotlib.pyplot as pl
import scipy.signal
import testtables
from sqltable import *  

def compressBuf(file):
  buf = open(file,'r').read()
  zbuf = cStringIO.StringIO()
  zfile = gzip.GzipFile(mode = 'wb',  fileobj = zbuf, compresslevel = 9)
  zfile.write(buf)
  zfile.close()
  return zbuf.getvalue()

def decompressBuf(buf):
  zbuf = StringIO.StringIO(buf)
  f = gzip.GzipFile(fileobj=zbuf)
  return f.read()

def is_number(s):
  try:
    float(s)
    return True
  except ValueError:
    pass

def col_count(cur, table):
  sql = 'pragma table_info(%s)' % (table)
  cur.execute(sql)
  return len(cur.fetchall())


def dict_to_list(dict):
  lst = []
  for i in sorted(dict.keys()):
    for j in dict[i]:
      if isinstance(j, list):
        lst.append(j)
      else:
        lst.append(dict[i])
        break
  return lst

def store_dict(cur, colName, table, data):
  cur.execute("select max(%s) from %s" % (colName, table))
  temp = cur.fetchone()[0]
  if temp is not None:
    newid = int(temp) + 1
  else:
    newid = 1
  lst = []
  for head in data:
    lst.append([newid, head, data[head]])
  sql = "INSERT into %s values(?,?,?)" % (table)
  cur.executemany(sql, lst)
  return newid


def load_dict(cur, table, idcol, idnum):
  sql = 'SELECT keyname,value from %s WHERE %s=%d' % (table, idcol, idnum)
  cur.execute(sql)
  a = cur.fetchall()
  dict = {}
  for row in a:
    dict[str(row[0])] = str(row[1])
  return dict

def guess_range(l):
  l=sorted(set(l))
  start=l[0]
  if len(l)>1:
    step=np.diff(l).min()
  else:
    step=None
  stop=l[-1]
  return start,stop,step

class SixDB(object):
  def __init__(self, studyDir='.'):
    print studyDir
    self.studyDir = studyDir
    if not (os.path.exists(studyDir+'/sixdeskenv') and \
      os.path.exists(studyDir+'/sysenv')):
      print "sixdeskenv and sysenv should both be present"
      sys.exit(0)
    self.env_var = sixdeskdir.parse_env(studyDir)
    self.env_var['env_timestamp']=str(time.time())
    env_var = self.env_var
    db = self.env_var['LHCDescrip'] + ".db"
    self.conn = sqlite3.connect(db, isolation_level="IMMEDIATE")
    cur = self.conn.cursor()
    cur.execute("PRAGMA synchronous = OFF")
    cur.execute("PRAGMA journal_mode = MEMORY")
    cur.execute("PRAGMA auto_vacuum = FULL")
    cur.execute("PRAGMA temp_store = MEMORY")
    cur.execute("PRAGMA count_changes = OFF")
    cur.execute("PRAGMA mmap_size=2335345345")
    self.conn.text_factory=str
    print "Opened database successfully"
    cols=SQLTable.cols_from_fields(testtables.Env.fields)
    tab = SQLTable(self.conn,'env',cols,testtables.Env.key)
    temp = tab.select('count(*)')[0][0]
    if temp > 0:
      print "study found updating..."
      lst = self.execute("select keyname,value from env")
      self.set_variable(lst)  
    else:
      print "study not found inserting..."
    self.st_env()

  def st_env(self):
    extra_files = []
    conn = self.conn
    cols=SQLTable.cols_from_fields(testtables.Env.fields)
    tab = SQLTable(conn,'env',cols,testtables.Env.key)
    cols=SQLTable.cols_from_fields(testtables.Files.fields)
    tab1 = SQLTable(conn,'files',cols,testtables.Files.key)
    cur = self.conn.cursor()
    env_var = self.env_var
    env_var['env_timestamp']=str(time.time())
    env_var = [[i,env_var[i]] for i in env_var.keys()]
    tab.insertl(env_var)
    path = os.path.join(self.studyDir, 'sixdeskenv')
    content = sqlite3.Binary(compressBuf(path))
    extra_files.append([path, content])
    path = os.path.join(self.studyDir, 'sysenv')
    content = sqlite3.Binary(compressBuf(path))
    extra_files.append([path, content])
    tab1.insertl(extra_files)

  def execute(self, sql):
    cur = self.conn.cursor()
    cur.execute(sql)
    self.conn.commit()
    return list(cur)

  def set_variable(self, lst):
    conn = self.conn
    env_var = self.env_var
    cols=SQLTable.cols_from_fields(testtables.Env.fields)
    tab = SQLTable(conn,'env',cols,testtables.Env.key)
    flag = 0
    upflag = 0
    for i in lst:
      if not ('env_timestamp' in str(i[0]) or str(i[0] in testtables.def_var)):
        if str(i[0]) in env_var.keys():
          if str(i[1]) != env_var[str(i[0])]:
            if is_number(str(i[1])) and is_number(env_var[str(i[0])]):
              if float(str(i[1])) != float(env_var[str(i[0])]):
                upflag = 1
            else:
              upflag = 1
            if upflag == 1:
              print 'variable',str(i[0]),'already present updating value from',
              print env_var[str(i[0])],'to',str(i[1])
              flag = 1
        else:
          print 'variable',str(i[0]),'not present adding'
          flag = 1
        env_var[str(i[0])] = str(i[1])
        upflag = 0
    if flag == 1:
      env_var['env_timestamp']=str(time.time())
    env_var = [[i,env_var[i]] for i in env_var.keys()]
    tab.insertl(env_var) 

  def info(self):     
    var = ['LHCDescrip', 'platform', 'madlsfq', 'lsfq', 'runtype', 'e0',
    'gamma', 'beam', 'dpini', 'istamad', 'iendmad', 'ns1l', 'ns2l', 'nsincl', 
    'sixdeskpairs', 'turnsl', 'turnsle', 'writebinl', 'kstep', 'kendl', 'kmaxl',
    'trackdir', 'sixtrack_input']
    env_var = self.env_var
    for keys in var:
      print '%s=%s'%(keys,env_var[keys])

  def st_control(self):
    extra_files = []
    conn = self.conn
    cols = SQLTable.cols_from_fields(testtables.Files.fields)
    tab = SQLTable(conn,'files',cols,testtables.Files.key)
    env_var = self.env_var
    workdir = env_var['sixdeskhome']
    beam = env_var['beam']
    if beam == "" or beam == "b1" or beam == "B1":
      appendbeam = ""
    elif beam == "b2" or beam == "B2":
      appendbeam = "_b2"
    else:
      print 'Unrecognised beam option must be null,b1,B1,b2 or B2'
      return
    files = 'fort.3.mother2_' + str(env_var['runtype']) + appendbeam
    path = os.path.join(workdir, 'control_files', files)
    content = sqlite3.Binary(compressBuf(path))
    path = path.replace(
      env_var['basedir'],'')
    extra_files.append([path, content])
    tab.insertl(extra_files)

  # def st_mask(self):
  #   extra_files = []
  #   env_var = self.env_var
  #   newid = self.newid
  #   conn = self.conn
  #   cols = SQLTable.cols_from_fields(testtables.Files.fields)
  #   tab = SQLTable(conn,'files',cols,testtables.Files.key)
  #   workdir = env_var['sixdeskhome']
  #   files = str(env_var['LHCDescrip']) + '.mask'
  #   path = os.path.join(workdir, 'mask', files)
  #   content = sqlite3.Binary(compressBuf(path))
  #   path = path.replace(
  #     env_var['basedir'],'')
  #   extra_files.append([newid, path, content])
  #   tab.insertl(extra_files)

  def st_mad6t_run(self):
    conn = self.conn
    cur = conn.cursor()
    env_var = self.env_var
    cols = SQLTable.cols_from_fields(testtables.Mad_Run.fields)
    tab = SQLTable(conn,'mad6t_run',cols,testtables.Mad_Run.key)
    cols = SQLTable.cols_from_fields(testtables.Files.fields)
    tab1 = SQLTable(conn,'files',cols,testtables.Files.key)
    rows = {}
    extra_files = []
    a = []
    workdir = env_var['sixtrack_input']
    a = tab.select('distinct run_id')
    if a:
      a = [str(i[0]) for i in a]
    col = col_count(cur, 'mad6t_run')
    for dirName, subdirList, fileList in os.walk(workdir):
      if 'mad.dorun' in dirName and not (dirName.split('/')[-1] in a):
        print 'found new mad run',dirName.split('/')[-1]
        for files in fileList:
          if not (files.endswith('.mask') or 'out' in files
              or files.endswith('log') or files.endswith('lsf')):
            seed = files.split('.')[-1]
            run_id = dirName.split('/')[-1]
            mad_in = sqlite3.Binary(
              compressBuf(os.path.join(dirName, files))
              )
            out_file = files.replace('.', '.out.')
            mad_out = sqlite3.Binary(
              compressBuf(os.path.join(dirName, out_file))
              )
            lsf_file = 'mad6t_' + seed + '.lsf'
            mad_lsf = sqlite3.Binary(
              compressBuf(os.path.join(dirName, lsf_file))
              )
            log_file = files.replace('.','_mad6t_')+'.log'
            mad_log = sqlite3.Binary(
              compressBuf(os.path.join(dirName, log_file))
              )
            time = os.path.getmtime(
              os.path.join(dirName, log_file)
              )
            rows[seed] = []
            rows[seed].append(
              [run_id, seed, mad_in, mad_out, mad_lsf, 
              mad_log, time]
              )
          if files.endswith('.mask'):  
            path = os.path.join(dirName, files)
            content = sqlite3.Binary(compressBuf(path))
            path = path.replace(
              env_var['basedir'],'')
            extra_files.append([path, content])
      if rows:
        lst = dict_to_list(rows)
        tab.insertl(lst)
        rows = {}
    if extra_files:
      tab1.insertl(extra_files)

  def st_mad6t_run2(self):
    conn = self.conn
    cur = conn.cursor()
    env_var = self.env_var
    cols = SQLTable.cols_from_fields(testtables.Files.fields)
    tab1 = SQLTable(conn,'files',cols,testtables.Files.key)
    workdir = env_var['sixtrack_input']
    extra_files = []
    col = col_count(cur, 'mad6t_run2')
    for dirName, subdirList, fileList in os.walk(workdir):
      for files in fileList:
        if 'fort.3' in files or files.endswith('.tmp'):
          path = os.path.join(dirName, files)
          content = sqlite3.Binary(compressBuf(path))
          path = path.replace(
            env_var['basedir'],'')
          extra_files.append([path, content])
    if extra_files:
      tab1.insertl(extra_files)

  def st_mad6t_results(self):
    conn = self.conn
    cur = conn.cursor()
    env_var = self.env_var
    cols = SQLTable.cols_from_fields(testtables.Mad_Res.fields)
    tab = SQLTable(conn,'mad6t_results',cols,testtables.Mad_Res.key)
    workdir = env_var['sixtrack_input']
    res = []
    rows = []
    ista = int(env_var['ista'])
    iend = int(env_var['iend'])
    flag = 0
    for i in range(ista,iend+1):
      rows = [i]
      files = 'fort.2_' + str(i) + '.gz'
      if os.path.exists(os.path.join(workdir,files)):
        rows.extend([sqlite3.Binary(open(
              os.path.join(workdir, files), 'r'
            ).read()
            )
            ])
        flag = 2
      else:
        print files,'missing insert null instead'
        rows.extend([''])
      files = files.replace('fort.2','fort.8')
      if os.path.exists(os.path.join(workdir,files)):
        rows.extend([sqlite3.Binary(open(
              os.path.join(workdir, files), 'r'
            ).read()
            )
            ])
        flag = 8
      else:
        print files,'missing insert null instead'
        rows.extend([''])
      files = files.replace('fort.8','fort.16')
      if os.path.exists(os.path.join(workdir,files)):
        rows.extend([sqlite3.Binary(open(
              os.path.join(workdir, files), 'r'
            ).read()
            )
            ])
        flag = 16
      else:
        print files,'missing insert null instead'
        rows.extend([''])
      if flag > 0:
        rows.extend(
          [os.path.getmtime(
            os.path.join(workdir, files.replace('fort.16','fort.'+str(flag)))
            )]
          )
      else:
        rows.extend([time.time()])
      res.append(rows)
      rows = []

    # for dirName, subdirList, fileList in os.walk(workdir):
    #   for files in fileList:
    #     if 'fort' in files and files.endswith('.gz'):
    #       head = int(files.split('_')[1].replace('.gz', ''))
    #       if head not in rows.keys():
    #         rows[head] = [head]
    #       if 'fort.2' in files:
    #         rows[head].insert(2, sqlite3.Binary(open(
    #           os.path.join(dirName, files), 'r'
    #         ).read()
    #         )
    #         )
    #       if 'fort.8' in files:
    #         rows[head].insert(3, sqlite3.Binary(open(
    #           os.path.join(dirName, files), 'r'
    #         ).read()
    #         )
    #         )
    #       if 'fort.16' in files:
    #         rows[head].extend([sqlite3.Binary(open(
    #           os.path.join(dirName, files), 'r'
    #         ).read()
    #         ),os.path.getmtime(os.path.join(dirName, files))
    #         ])
    #       if len(rows[head]) == 5:
    #         print rows[head]
    if res:
      # lst = dict_to_list(rows)
      print "length of row of result is",len(res)
      tab.insertl(res)
      rows = {}

  def st_six_beta(self):
    conn = self.conn
    cur = conn.cursor()
    env_var = self.env_var
    cols = SQLTable.cols_from_fields(testtables.Six_Be.fields)
    tab = SQLTable(conn,'six_beta',cols,testtables.Six_Be.key)
    cols = SQLTable.cols_from_fields(testtables.Files.fields)
    tab1 = SQLTable(conn,'files',cols,testtables.Files.key)
    workdir = os.path.join(env_var['sixdesktrack'],env_var['LHCDescrip'])
    rows = {}
    extra_files = []
    col = col_count(cur, 'six_beta')
    beta = six = gen = []
    for dirName, subdirList, fileList in os.walk(workdir):
      for files in fileList:
        if 'general_input' in files:
          with open(os.path.join(dirName, files), 'r') as FileObj:
            for lines in FileObj:
              gen = lines.split()
          path = os.path.join(dirName, files)
          content = sqlite3.Binary(compressBuf(path))
          path = path.replace(
            env_var['basedir'],'')
          extra_files.append([path, content])
        if 'betavalues' in files or 'sixdesktunes' in files:
          dirn = dirName.replace(workdir + '/', '')
          dirn = dirn.split('/')
          seed = int(dirn[0])
          tunex, tuney = [i for i in dirn[2].split('_')]
          if not (seed in rows.keys()):
            rows[seed] = []
          temp = [seed, tunex, tuney]
          if 'betavalues' in files:
            f = open(os.path.join(dirName, files), 'r')
            beta = [float(i) for i in f.read().split()]
          if 'sixdesktunes' in files:
            f = open(os.path.join(dirName, files), 'r')
            six = [float(i) for i in f.read().split()]
          f.close()
        if beta and temp and six:
          rows[seed].append(temp + beta + gen + six)
          beta = temp = six = []
    if rows:
      lst = dict_to_list(rows)
      tab.insertl(lst)
    if extra_files:
      tab1.insertl(extra_files)

  def st_six_input(self):
    conn = self.conn
    cur = conn.cursor()
    env_var = self.env_var
    cols = SQLTable.cols_from_fields(testtables.Six_In.fields)
    tab = SQLTable(conn,'six_input',cols,testtables.Six_In.key)
    cols = SQLTable.cols_from_fields(testtables.Files.fields)
    tab1 = SQLTable(conn,'files',cols,testtables.Files.key)
    workdir = os.path.join(env_var['sixdesktrack'],env_var['LHCDescrip'])
    extra_files = []
    rows = []
    six_id = 1
    cmd = """find %s -name 'fort.3.gz'"""%(workdir)
    print cmd
    a = os.popen(cmd).read().split('\n')[:-1]
    for dirName in a:
      files = dirName.split('/')[-1]
      dirName = dirName.replace('/'+files,'')
      if not ('-' in dirName):
        dirn = dirName.replace(workdir + '/', '')
        dirn = re.split('/|_', dirn)
        dirn = [six_id] + dirn
        dirn.extend([sqlite3.Binary(open(
          os.path.join(dirName, files), 'r'
        ).read()
        )])
        rows.append(dirn)
        dirn = []
        six_id += 1
    if rows:
      tab.insertl(rows)
      rows = []
    cmd = """find %s -name '*.log' -o -name '*.lsf'"""%(workdir)
    print cmd
    a = os.popen(cmd).read().split('\n')[:-1]
    for dirName in a:
      files = dirName.split('/')[-1]
      dirName = dirName.replace('/'+files,'')
      path = os.path.join(dirName, files)
      content = sqlite3.Binary(compressBuf(path))
      path = path.replace(env_var['basedir'],'')
      extra_files.append([path, content])  
    # if rows:
    #   tab.insertl(rows)
    if extra_files:
      tab1.insertl(extra_files)

  def st_six_results(self):
    conn = self.conn
    cur = conn.cursor()
    env_var = self.env_var
    cols = SQLTable.cols_from_fields(testtables.Six_In.fields)
    tab = SQLTable(conn,'six_input',cols,testtables.Six_In.key)
    workdir = os.path.join(env_var['sixdesktrack'],env_var['LHCDescrip'])
    rows = []
    col = col_count(cur,'six_results')
    inp = tab.select("""distinct id,seed,simul,tunex,tuney,amp1,amp2,turns,
        angle""")
    inp = [[str(i) for i in j] for j in inp]
    cols = SQLTable.cols_from_fields(testtables.Six_Res.fields)
    tab = SQLTable(conn,'six_results',cols,testtables.Six_Res.key)
    cmd = "find %s -name 'fort.10.gz'"%(workdir)
    print cmd
    a = os.popen(cmd).read().split('\n')[:-1]
    for dirName in a:
      files = dirName.split('/')[-1]
      dirName = dirName.replace('/fort.10.gz','')
      if 'fort.10' in files and not '-' in dirName:
        dirn = dirName.replace(workdir+'/','')
        dirn = re.split('/|_',dirn)
        for i in [2,3,4,5,7]:
          if not ('.' in str(dirn[i])): 
            dirn[i] += '.0'
        for i in xrange(len(inp)+1):
          if i == len(inp):
            print 'fort.3 file missing for',
            print dirName.replace(env_var['sixdesktrack']+'/','')
            print 'create file and run again'
            print dirn
            exit(0)
          if dirn == inp[i][1:]:
            six_id = inp[i][0]
            break
        with gzip.open(os.path.join(dirName,files),"r") as FileObj:
          count = 1
          for lines in FileObj:
            rows.append([six_id,count]+lines.split())
            count += 1
        if len(rows) > 180000:
          tab.insertl(rows)
          rows = []
    if rows:
      tab.insertl(rows)

  def get_missing_fort10(self):
    conn = self.conn
    cur = conn.cursor()
    env_var = self.env_var
    # newid = self.newid
    sql = """select seed,tunex,tuney,amp1,amp2,turns,angle from six_input
    where not exists(select 1 from six_results where id=six_input_id)"""
    a = self.execute(sql)
    if a:
      for rows in a:
        print 'fort.10 missing at','/'.join([str(i) for i in rows])
        print 
      return 1
    else:
      return 0

  def get_incomplete_fort10(self):
    conn = self.conn
    cur = conn.cursor()
    env_var = self.env_var
    # newid = self.newid
    sql = """select seed,tunex,tuney,amp1,amp2,turns,angle from six_input
    where not exists(select 1 from six_results where id=six_input_id and 
    row_num=30)"""
    a = self.execute(sql)
    if a:
      for rows in a:
        print 'fort.10 incomplete at','/'.join([str(i) for i in rows])
        print 
      return 1
    else:
      return 0

  def inspect_results(self):
    names='seed,tunex,tuney,amp1,amp2,turns,angle'
    for name in names.split(','):
      sql="SELECT DISTINCT %s FROM six_input"%name
      print sql
      data=[d[0] for d in self.execute(sql)]
      print name, guess_range(data)

  def iter_job_params(self):
    names="""b.value,a.seed,a.tunex,a.tuney,a.amp1,a.amp2,a.turns,a.angle,
        c.row_num"""
    sql="""SELECT DISTINCT %s FROM six_input as a,env as b,six_results as c
        where a.id=c.six_input_id and b.keyname='LHCDescrip'"""%names
    return self.conn.cursor().execute(sql)
    
  def iter_job_params_comp(self):
    names='seed,tunex,tuney,amp1,amp2,turns,angle'
    sql='SELECT DISTINCT %s FROM six_input'%names
    return self.conn.cursor().execute(sql)
  
  def get_num_results(self):
    return self.execute('SELECT count(*) from six_results')[0][0]/30

  def get_seeds(self):
    env_var = self.env_var
    ista = int(env_var['ista'])
    iend = int(env_var['iend'])
    return range(ista,iend+1)

  def get_angles(self):
    env_var = self.env_var
    kmaxl = int(env_var['kmaxl'])
    kinil = int(env_var['kinil'])
    kendl = int(env_var['kendl'])
    kstep = int(env_var['kstep'])
    s=90./(kmaxl+1)
    return np.arange(kinil,kendl+1,kstep)*s

  def get_amplitudes(self):
    env_var = self.env_var
    nsincl = float(env_var['nsincl'])
    ns1l = float(env_var['ns1l'])
    ns2l = float(env_var['ns2l'])
    return [(a,a+nsincl) for a in np.arange(ns1l,ns2l,nsincl)]

  def iter_tunes(self):
    env_var = self.env_var
    qx = float(env_var['tunex'])
    qy = float(env_var['tuney'])
    while qx <= float(env_var['tunex1']) and qy <= float(env_var['tuney1']):
      yield qx,qy
      qx += float(env_var['deltax'])
      qy += float(env_var['deltay'])

  def get_tunes(self):
    return list(self.iter_tunes())

  def gen_job_params(self):
    turnsl = '%E'%(float(self.env_var['turnsl']))
    turnsl = 'e'+str(int(turnsl.split('+')[1]))
    for seed in self.get_seeds():
      for tunex,tuney in self.get_tunes():
        for amp1,amp2 in self.get_amplitudes():
          for angle in self.get_angles():
            yield (seed,tunex,tuney,amp1,amp2,turnsl,angle)

  def get_missing_jobs(self):
    cur = self.conn.cursor()
    turnsl = '%E'%(float(self.env_var['turnsl']))
    turnsl = 'e'+str(int(turnsl.split('+')[1]))
    a = self.execute("""SELECT seed,tunex,tuney,amp1,amp2,turns,angle from 
      six_input where turns='%s'"""%(turnsl))
    print a[0]
    for rows in self.gen_job_params():
      if rows not in a:
        print 'missing job',rows

  def inspect_jobparams(self):
    data=list(self.iter_job_params())
    names='study,seed,tunex,tuney,amp1,amp2,turns,angle,row'.split(',')
    data=dict(zip(names,zip(*data)))
  #    for name in names:
  #      print name, guess_range(data[name])
  #    print 'results found',len(data['seed'])
    turns=list(set(data['turns']))
    p={}
    p['ista'],p['iend'],p['istep']=guess_range(data['seed'])
    p['tunex'],p['tunex1'],p['deltax']=guess_range(data['tunex'])
    p['tuney'],p['tuney1'],p['deltay']=guess_range(data['tuney'])
    if p['deltax'] is None:
      p['deltax']=0.0001
    if p['deltay'] is None:
      p['deltay']=0.0001
    a1,a2,ast=guess_range(data['angle'])
    p['kmaxl']=90/ast-1
    p['kinil']=a1/ast
    p['kendl']=a2/ast
    p['kstep']=1
    p['ns1l'],p['ns2l'],p['nsincl']=guess_range(data['amp1']+data['amp2'])
    p['turnsl']=max(data['turns'])
    p['sixdeskpairs']=max(data['row'])+1
    p['LHCDescrip']=str(data['study'][0])
    return p
    
  def get_survival_turns(self,seed):
    cmd="""SELECT angle,amp1+(amp2-amp1)*row_num/30,
        CASE WHEN sturns1 < sturns2 THEN sturns1 ELSE sturns2 END
        FROM six_results,six_input WHERE seed=%s and id=six_input_id
        ORDER BY angle,sigx1"""
    # cmd="""SELECT angle,sqrt(sigx1*2+sigy1*2),
    #         CASE WHEN sturns1 < sturns2 THEN sturns1 ELSE sturns2 END
    #         FROM six_results,six_input WHERE seed=%s and id=six_input_id 
    #         ORDER BY angle,sigx1"""

    cur=self.conn.cursor().execute(cmd%seed)
    ftype=[('angle',float),('amp',float),('surv',float)]
    data=np.fromiter(cur,dtype=ftype)
    angles=len(set(data['angle']))
    return data.reshape(angles,-1)
    
  def plot_survival_2d(self,seed,smooth=None):
    data=self.get_survival_turns(seed)
    a,s,t=data['angle'],data['amp'],data['surv']
    self._plot_survival_2d(a,s,t,smooth=smooth)
    pl.title('Seed %d survived turns'%seed)
    
  def plot_survival_2d_avg(self,smooth=None):
    cmd=""" SELECT seed,angle,amp1+(amp2-amp1)*row_num/30,
        CASE WHEN sturns1 < sturns2 THEN sturns1 ELSE sturns2 END
        FROM six_results,six_input WHERE id=six_input_id
        ORDER BY angle,sigx1"""
    cur=self.conn.cursor().execute(cmd)
    ftype=[('seed',float),('angle',float),('amp',float),('surv',float)]
    data=np.fromiter(cur,dtype=ftype)
    angles=len(set(data['angle']))
    seeds=len(set(data['seed']))
    data=data.reshape(seeds,angles,-1)
    a,s,t=data['angle'],data['amp'],data['surv']
    a=a.mean(axis=0); s=s.mean(axis=0); t=t.mean(axis=0);
    self._plot_survival_2d(a,s,t,smooth=smooth)
    pl.title('Survived turns')
    
  def _plot_survival_2d(self,a,s,t,smooth=None):
    rad=np.pi*a/180
    x=s*np.cos(rad)
    y=s*np.sin(rad)
    #t=np.log10(t)
    if smooth is not None:
      if type(smooth)==int:
        smooth=np.ones((1.,smooth))/smooth
      elif type(smooth)==tuple:
        smooth=np.ones(smooth)/float(smooth[0]*smooth[1])
        t=scipy.signal.fftconvolve(smooth,t,mode='full')
    pl.pcolormesh(x,y,t,antialiased=True)
    pl.xlabel(r'$\sigma_x$')
    pl.ylabel(r'$\sigma_y$')
    pl.colorbar()
    
  def plot_survival_avg(self,seed):
    data=self.get_survival_turns(seed)
    a,s,t=data['angle'],data['amp'],data['surv']
    rad=np.pi*a/180
    drad=rad[0,0]
    slab='Seed %d'%seed
    #savg2=s**4*np.sin(2*rad)*drad
    pl.plot(s.mean(axis=0),t.min(axis=0) ,label='min')
    pl.plot(s.mean(axis=0),t.mean(axis=0),label='avg')
    pl.plot(s.mean(axis=0),t.max(axis=0) ,label='max')
    pl.ylim(0,pl.ylim()[1]*1.1)
    pl.xlabel(r'$\sigma$')
    pl.ylabel(r'survived turns')
    pl.legend(loc='lower left')
    return data
    
  def plot_survival_avg2(self,seed):
    def mk_tuple(a,s,t,nlim):
      region=[]
      for ia,ts in enumerate(t):
        cond=np.where(ts<=nlim)[0]
        #print ts[cond]
        if len(cond)>0:
          it=cond[0]
        else:
          it=-1
        region.append((ia,it))
        #print ts[it],s[ia,it]
      region=zip(*region)
      #print t[region]
      tmin=t[region].min()
      tavg=t[region].mean()
      tmax=t[region].max()
      savg=s[region].mean()
      rad=np.pi*a[region]/180
      drad=rad[0]
      savg2=np.sum(s[region]**4*np.sin(2*rad)*drad)**.25
      return nlim,tmin,tavg,tmax,savg,savg2
    data=self.get_survival_turns(seed)
    a,s,t=data['angle'],data['amp'],data['surv']
    table=np.array([mk_tuple(a,s,t,nlim) for nlim \
      in np.arange(0,1.1e6,1e4)]).T
    nlim,tmin,tavg,tmax,savg,savg2=table
    pl.plot(savg,tmin,label='min')
    pl.plot(savg,tavg,label='avg')
    pl.plot(savg,tmax,label='max')
    return table

if __name__ == '__main__':
  a = SixDB('/home/monis/Desktop/GSOC/files/w7/sixjobs/')
  a.st_control()
  # a.st_mask()
  a.st_mad6t_run()
  a.st_mad6t_run2()
  a.st_mad6t_results()
  a.st_six_beta()
  a.st_six_input()
  a.st_six_results()
  exit(0)
  a.get_missing_jobs()
  a.get_missing_fort10()
  # exit(0)
  # print a.get_num_results()
  # print a.inspect_jobparams()
  # a.plot_survival_2d(1)
  # a.plot_survival_2d(2)
  # a.plot_survival_avg(1)
  jobs = lsfqueue.parse_bjobs()
  if jobs:
    jobs_stats(jobs)

