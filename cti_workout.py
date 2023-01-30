#! /usr/bin/env python3

import time
import numpy
import pyvisa
import sqlite3
from pymeasure.instruments.racal import Racal1992

def psu_check(inst):
    r =  inst.query("*IDN?")

    model = r.split(',')[1]
    assert model=="E3631A"

def psu_set_voltage_current(inst,v,c):
    inst.write("APPLY P6V,%f,%f" % (v,c))

def psu_output_state(inst, state):
    inst.write(f"output:state {state}")

def psu_measure_voltage_current(inst):
    v = float(inst.query("MEASURE:VOLTAGE? P6V"))
    c = float(inst.query("MEASURE:CURRENT? P6V"))
    return(v,c)

def acq_check(inst):
    r =  inst.query("*IDN?")
    model = r.split(',')[1]
    assert model=="34970A"

def acq_set_dac(inst, v):
    assert v>= 0.0 and v<=4.0

    acq.write("source:voltage %f,(@104)" % (v))

def acq_conf_temp(inst):
    acq.write("conf:temp tc,k,(@201)")
    acq.write("unit:temp c,(@201)")
    acq.write("route:scan (@201)")

def acq_get_temp(inst):
    return float(acq.query("read?"))

rm=pyvisa.ResourceManager()
psu=rm.open_resource("GPIB::5")
psu_check(psu)
acq=rm.open_resource("GPIB::9")
acq_check(acq)
racal=Racal1992("GPIB::14")

def create_db(filename):
    conn=sqlite3.connect(filename)
    c = conn.cursor()
    c.execute('''
        create table if not exists measurements(
            [id]            integer primary key,
            [session_id]    integer,
            [created]       integer,
            [psu_set_v]     real,
            [psu_set_c]     real,
            [psu_meas_v]    real,
            [psu_meas_c]    real,
            [freq]          real,
            [vref]          real,
            [temp]          real)
        ''')
    c.execute('''
        create table if not exists sessions(
            [id]            integer primary key,
            [name]          text,
            [description]   text,
            [created]       text)
        ''')
    conn.commit()

    return conn

def create_session(conn, name, description=''):
    sql = '''insert into sessions(name, description,created)
             values(?, ?, datetime('now'))'''

    c = conn.cursor()
    c.execute(sql, (name, description))
    conn.commit()

    return c.lastrowid
    
def record_measurement(conn, session_id, psu_set_v=None, psu_set_c=None, psu_meas_v=None, psu_meas_c=None, freq=None, vref=None, temp=None):
    sql = '''insert into measurements(session_id, created, psu_set_v, psu_set_c, psu_meas_v, psu_meas_c, freq, vref, temp)
             values(?, datetime('now'), ?, ?, ?, ?, ?, ?, ?)'''

    if psu_set_v is None:
        # TODO: Read from psu...
        assert False

    if psu_set_c is None:
        # TODO: Read from psu...
        assert False

    if psu_meas_v is None or psu_meas_c is None:
        meas_v, meas_c = psu_measure_voltage_current(psu)

        if psu_meas_v is None:
            psu_meas_v = meas_v

        if psu_meas_c is None:
            psu_meas_c = meas_c

    if freq is None:
        racal.wait_for_measurement()
        time.sleep(0.1)
        freq = racal.measured_value

    if vref is None:
        # TODO: Read from acq...
        assert False

    if temp is None:
        # Read from acq...
        temp = acq_get_temp(acq)

    c = conn.cursor()
    print("record: ", (session_id, psu_set_v, psu_set_c, psu_meas_v, psu_meas_c, freq, vref, temp))
    c.execute(sql, (session_id, psu_set_v, psu_set_c, psu_meas_v, psu_meas_c, freq, vref, temp))
    conn.commit()


conn=create_db("test.db")

psu_set_voltage_current(psu, 5.0, 0.6)
psu_measure_voltage_current(psu)

acq_conf_temp(acq)

acq_set_dac(acq, 2.0)

racal.channel_settings('A', 
            coupling="DC", 
            impedance='1M', 
            slope='pos',
            trigger='auto',
            filtering=False,
            trigger_level=1.5)
racal.operating_mode('frequency_a')

def test_xtal_warmup(xtal_vdd, length_s):
    cur_session = create_session(conn, f"xtal warmup vdd={xtal_vdd}", 
        f"warm up xtal for {length_s} seconds")

    print(f"session id: {cur_session}")

    psu_set_v  = xtal_vdd
    psu_set_c  = 0.6
    vref       = 2.0

    acq_set_dac(acq, vref)
    psu_set_voltage_current(psu, psu_set_v, psu_set_c)
    psu_output_state(psu, "on")
    racal.resolution=9
    res=9

    t_begin  =time.time()
    t_end   = t_begin + length_s
    while time.time() < t_end:
        if time.time()-t_begin>10*60 and res==9:
            # After XTAL warmup, measure less but at higher accuracy
            racal.resolution=10
            res=10
        record_measurement(conn, cur_session, psu_set_v=psu_set_v, psu_set_c=psu_set_c, psu_meas_v=None, psu_meas_c=None, freq=None, vref=vref, temp=None)
    
def test_xtal_long_term(xtal_vdd, length_s):
    cur_session = create_session(conn, f"long term run after warmup vdd={xtal_vdd}", 
        f"warm up xtal for {length_s} seconds")

    print(f"session id: {cur_session}")

    psu_set_v  = xtal_vdd
    psu_set_c  = 0.6
    vref       = 2.0

    acq_set_dac(acq, vref)
    psu_set_voltage_current(psu, psu_set_v, psu_set_c)
    psu_output_state(psu, "on")
    racal.resolution=10

    t_begin  =time.time()
    t_end   = t_begin + length_s
    while time.time() < t_end:
        record_measurement(conn, cur_session, psu_set_v=psu_set_v, psu_set_c=psu_set_c, psu_meas_v=None, psu_meas_c=None, freq=None, vref=vref, temp=None)

def test_freq_vs_vref(xtal_vdd):
    cur_session = create_session(conn, f"freq vs vref",
        f"change vref from 0 to 4V, record freq")

    psu_set_v  = xtal_vdd
    psu_set_c  = 0.6
    step       = 0.01

    acq_set_dac(acq, 0)
    psu_set_voltage_current(psu, psu_set_v, psu_set_c)
    psu_output_state(psu, "on")
    racal.resolution=9
    print(f"resolution: {racal.resolution}")
    
    for vref in numpy.arange(0.0, 4.0+step, step):
        print(f"vref: {vref}")
        acq_set_dac(acq, vref)
        record_measurement(conn, cur_session, psu_set_v=psu_set_v, psu_set_c=psu_set_c, psu_meas_v=None, psu_meas_c=None, freq=None, vref=vref, temp=None)

def test_vdd_steps(repeats, time_between_steps, vdd_min, vdd_max, resolution=10):
    cur_session = create_session(conn, f"vdd_steps",
        f"change xtal vdd from f{vdd_min} to f{vdd_max} and back every f{time_between_steps} seconds, record freq")

    psu_set_v  = vdd_min
    psu_set_c  = 0.6
    vref       = 2.0

    acq_set_dac(acq, vref)
    psu_set_voltage_current(psu, psu_set_v, psu_set_c)
    psu_output_state(psu, "on")
    racal.resolution=resolution

    for r in range(repeats):
        print(f"repeat: {r}")
        psu_set_v = vdd_min
        psu_set_voltage_current(psu, psu_set_v, psu_set_c)

        t_begin = time.time()
        t_end   = t_begin + time_between_steps
        while time.time() < t_end:
            record_measurement(conn, cur_session, psu_set_v=psu_set_v, psu_set_c=psu_set_c, psu_meas_v=None, psu_meas_c=None, freq=None, vref=vref, temp=None)

        psu_set_v = vdd_max
        psu_set_voltage_current(psu, psu_set_v, psu_set_c)

        t_begin = time.time()
        t_end   = t_begin + time_between_steps
        while time.time() < t_end:
            record_measurement(conn, cur_session, psu_set_v=psu_set_v, psu_set_c=psu_set_c, psu_meas_v=None, psu_meas_c=None, freq=None, vref=vref, temp=None)

#test_xtal_warmup(5.0, 7200)
#test_xtal_long_term(5.0, 8 * 3600)  # 8 hours
#test_freq_vs_vref(5.0)
#test_vdd_steps(repeats=50, time_between_steps=35, vdd_min=4.80, vdd_max=5.20, resolution=10)

psu_set_voltage_current(psu, 4.75, 0.6)
time.sleep(60)
test_freq_vs_vref(4.75)
psu_set_voltage_current(psu, 5, 0.6)
time.sleep(60)
test_freq_vs_vref(5)
psu_set_voltage_current(psu, 5.25, 0.6)
time.sleep(60)
test_freq_vs_vref(5.25)

