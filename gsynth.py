#!/usr/bin/python3
# -*- coding: UTF-8 -*-

"""
gsynth.py - GeigerLog tools for synthetic data

include in programs with:
    include gsynth
"""

###############################################################################
#    This file is part of GeigerLog.
#
#    GeigerLog is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    GeigerLog is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with GeigerLog.  If not, see <http://www.gnu.org/licenses/>.
###############################################################################

__author__          = "ullix"
__copyright__       = "Copyright 2016, 2017, 2018, 2019"
__credits__         = [""]
__license__         = "GPL3"

from   gutils       import *



def createSyntheticLog():
    """Create synthetic data and save in log format. All times in SECONDS"""

    fprint(header("Create Synthetic Log CSV file"))

    records     = 20000
    #cycletime   = 60.0     # in seconds
    cycletime   = 1.0       # in seconds
    mode        = "CPS"
    #mode        = "CPM"

    mean        = 30
    stddev      = np.sqrt(mean)

# get time
    t = np.float64(np.array(list(range(0, records)))) * cycletime
    print("time: size: {}, Delta-t: {} sec".format(t.size, (t[1] - t[0])))
    print(np.int_(t))

    # convert time in sec to datetime strings
    strt0 = "2018-01-03 00:00:00"          # nominal default start datetime
    t0    = mpld.datestr2num(strt0)        # time zero
    td    = np.empty(records, dtype='U19') # holds strings of max length 19
    print("td, len:", td.size, td)
    for i in range(0, records):
        td[i] = mpld.num2date(t0 + t[i] / 86400.) #clipped after 19 chars

# get data
    sigt, DataSrc     = getWhiteNoisePoisson(records, mean, cycletime, mode)     # White Noise from Poisson Distribution
    #sigt, DataSrc    = getWhiteNoiseNormal(records, mean=mean, stddev=stddev)    # White Noise from Normal Distribution
    #sigt, DataSrc    = getSinus(records, t)                                      # Sine (one or more)
    #sigt, DataSrc    = getWhiteNoiseSine(records, t)                             # White Noise with Sine
    #sigt, DataSrc    = getConstantData(records, t)                               # constant + breaks
    #sigt, DataSrc    = getAutocorr(records)                                      # Autocorr as time function
    #sigt, DataSrc    = getRectangle(records)                                     # Rectangle of 20 samples @ 3sec = 1min
    #sigt, DataSrc    = getWhiteNoisePoissonAutocorr(records, mean, cycletime)    # Autocorrelated Poisson Noise
    #sigt, DataSrc    = getRandomData(records, mean, stddev)                      # Radom Data

    # Mean=17, followed by mean=29
    #sigt1, DataSrc     = getWhiteNoisePoisson(20000, mean=17)                    # White Noise from Poisson Distribution
    #sigt2, DataSrc2    = getWhiteNoisePoisson(20000, mean=29)                    # White Noise from Poisson Distribution
    #sigt = np.concatenate((sigt1 , sigt2))
    #print "len(sigt):", len(sigt)
    #DataSrc = "WhiteNoisePoisson,mean=17&29CPM"

    fprint("Using Datasource:", DataSrc)
    fprint("No of records:", records)

    for i in range(0, 10): print("i: {:4d}, time(sec): {:5.2f}, sigt: {}".format(i, t[i] * 60., sigt[i]))
    print("...")
    for i in range(0, records, int(records/10.)): print("i: {:4d}, time(min): {:5.2f}, sigt: {}".format(i, t[i], sigt[i]))

# write to log file
    path = gglobs.dataPath + "/" + DataSrc + ".log"
    writeFileW(path, "", linefeed = True)
    writeFileA(path, "#HEADER ," + strt0 + ", SYNTHETIC data: " + DataSrc)
    writeFileA(path, "#LOGGING," + strt0 + ", Start: cycle {} sec, mode '{}', device 'SYNTHETIC'".format(cycletime, mode))
    for i in range(records):
        writestring = " {:7d},{:19s}, {:}".format(i, td[i], sigt[i])
        writeFileA(path, writestring)

    fprint("Created file: " + path)


def getWhiteNoisePoisson(records, mean, cycletime, mode):
    """White noise data drawn from Poisson distribution"""

    DataSrc = "WhiteNoisePoisson, mean={}, cycle={}, mode={}".format(mean, cycletime, mode)

    x = np.random.poisson(mean, size=records )
    print("x.size, x.mean, x.var, x.std. :", x.size, np.mean(x), np.var(x), np.std(x))
    print(x)

    return x, DataSrc


def getWhiteNoisePoissonAutocorr(records, mean, cycletime):
    """White noise data drawn from Poisson distribution"""

    DataSrc = "Autocorrelated Poisson Noise, CPM={}, cycle={}sec".format(mean, cycletime)

    x    = np.random.poisson(mean / 60., size=records * 60 + 60 )
    print("x.size, x.mean, x.var, x.std. :", x.size, np.mean(x), np.var(x), np.std(x))
    print(x)

    x2   = np.zeros(records)
    print("all zeros: x2.size, x2.mean, x2.var, x2.std. :", x2.size, np.mean(x2), np.var(x2), np.std(x2))

    for i in range(0, records):
        j = i * cycletime
        x2[i] = np.sum(x[j : j + 60])

    print("x2.size, x2.mean, x2.var, x2.std. :", x2.size, np.mean(x2), np.var(x2), np.std(x2))

    return x2, DataSrc


def getSinus(records, t):
    """
    sinus data
    All times in seconds
    """

    DataSrc = "Sinus"
    pi2     = 2.0 * np.pi

    x   = 10.0 + 5.0 * np.sin(t * pi2 / (100. * 60. +  0. )  ) # periode von 100   min
    x  +=  0.0 + 5.0 * np.sin(t * pi2 / (400. * 60. +  0. )  ) # periode von 400   min
    x  +=  0.0 + 5.0 * np.sin(t * pi2 / ( 30. * 60. +  0. )  ) # periode von  50   min
    x  +=  0.0 + 5.0 * np.sin(t * pi2 / (  3. * 60. +  4. )  ) # periode von   3.x min
    x  +=  0.0 + 5.0 * np.sin(t * pi2 / (  3. * 60. +  9. )  ) # periode von   3.y min
    x  +=  0.0 + 5.0 * np.sin(t * pi2 / (  3. * 60. + 13. )  ) # periode von   3.z min
    x  +=  0.0 + 5.0 * np.sin(t * pi2 / (  1.0            )  ) # periode von   1   sec
    x  +=  0.0 + 5.0 * np.sin(t * pi2 / (  0.5            )  ) # periode von   0.5 sec

    return x, DataSrc


def getConstantData(records, t):
    """
    constant data
    All times in seconds
    """

    DataSrc = "Constant + Breaks"
    x       = np.ones(records) * 1000

    for i in range(0, records - 10, 20):
        x[i] = 500.
        x[i + 1] = -10.
        x[i + 2] = 1.

    return x, DataSrc


def getWhiteNoiseNormal(records, mean=16, stddev=4):
    """
    White noise data
    All times in seconds
    """

    DataSrc = "WhiteNoiseNormal, mean={}, stddev={:3.2f}".format(mean, stddev)
    x       = np.random.normal(mean, stddev, size=records)

    return x, DataSrc


def getAutocorr(records):
    """
    The autocorrelation function as time series to use as input
    All times in seconds
    """

    DataSrc = "Autocorrelation as time series - 1st point=1"

    # a small random component
    mean = 0
    std  = 0.01
    x    = np.random.normal(mean, std, size=records)

    #for a 1 sec cycle time the first 60 records will show a linear down curve
    #for i in range (0, 20):
    #    x[i] = 1 - i * 1./20.

    x[0] = 1


    return x, DataSrc


def getRectangle(records):
    """
    A rectangle 1 min long with 20 samples @ assumed 3sec cycle
    """

    DataSrc = "Rectangle_1min"
    x       = np.zeros(records)
    #print x
    for i in range(20):
        x[i] = 1
    print("x:", len(x), x)

    return x, DataSrc


def getWhiteNoiseSine(records, t):
    """
    White noise with Sine data
    All times in seconds
    """

    DataSrc = "WhiteNoiseNormal + Sine"
    pi2     = 2.0 * np.pi

    mean = 2500
    std  = np.sqrt(mean)
    x    = np.random.normal(mean, std, size=records)
    p1   = (100. * 60. + 1.4) / 60.  # 100,0333 min
    print("getWhiteNoiseSinusData: p1:", p1)
    x   +=  40. * std * (np.sin(t * pi2 / p1 ))
    x   +=  10. * std * (np.sin(t * pi2 / 11. ))

    return x, DataSrc


def getRandomData(records, mean, stddev):
    """random data"""

    DataSrc = "Random Data, mean={}, Uniform 0...{}".format(mean, mean*2)

    x = mean * 2 * np.random.rand(records)
    print(DataSrc, x)

    return x, DataSrc

    """White noise data drawn from Poisson distribution"""

    DataSrc = "Autocorrelated Poisson Noise, CPM={}, cycle={}sec".format(mean, cycletime)

    x    = np.random.poisson(mean / 60., size=records * 60 + 60 )
    print("x.size, x.mean, x.var, x.std. :", x.size, np.mean(x), np.var(x), np.std(x))
    print(x)

    x2   = np.zeros(records)
    print("all zeros: x2.size, x2.mean, x2.var, x2.std. :", x2.size, np.mean(x2), np.var(x2), np.std(x2))

    for i in range(0, records):
        j = i * cycletime
        x2[i] = np.sum(x[j : j + 60])

    print("x2.size, x2.mean, x2.var, x2.std. :", x2.size, np.mean(x2), np.var(x2), np.std(x2))

    return x2, DataSrc


    """random data"""

    DataSrc = "Random Data, mean={}, Uniform 0...{}".format(mean, mean*2)

    x = mean * 2 * np.random.rand(records)
    print(DataSrc, x)

    return x, DataSrc
