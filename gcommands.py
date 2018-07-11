#!/usr/bin/python
# -*- coding: UTF-8 -*-

"""
gcommands.py - the commands specific to the Geiger counter

using serial communication

device command coding taken from:
Phil Gillaspy, https://sourceforge.net/projects/gqgmc/
and document GQ-RFC1201.txt (GQ-RFC1201, GQ Geiger Counter Communication
Protocol, Ver 1.40    Jan-2015)
"""


import sys                      # system functions
import serial
import serial.tools.list_ports  # allows listing of serial ports
import time
import datetime                 # date and time conversions
import struct                   # packing numbers into chars
import traceback                # for traceback on error

from gutils import *

__author__      = "ullix"
__copyright__   = "Copyright 2016"
__credits__     = ["Phil Gillaspy"]
__license__     = "GPL"


#
# Commands and functions implemented in device
#

def getVER(ser):
    # Get hardware model and version
    # send <GETVER>> and read 14 bytes
    # returns total of 14 bytes ASCII chars from GQ GMC unit.
    # includes 7 bytes hardware model and 7 bytes firmware version.
    # e.g.: GMC-300Re 4.20
    # use byteformat=False to NOT convert into int but return ASCII string

    rec = serialCOMM(ser, b'<GETVER>>', 14, orig(__file__), False)
    dprint(gglobs.debug, "getVER:", rec)

    return rec


def getCPMS(ser, CPMflag = True):
    # Get current CPM or CPS value
    # if CPMflag=True get CPM, else get CPS
    # if CPM:     send <GETCPM>> and read 2 bytes
    # if CPS:     send <GETCPS>> and read 2 bytes
    # In total 2 bytes data are returned from GQ GMC unit
    # in CPM:
    # as a 16 bit unsigned integer.
    # The first byte is MSB byte data and second byte is LSB byte data.
    # e.g.: 00 1C  -> the returned CPM is 28
    # e.g.: 0B EA  -> the returned CPM is 3050
    #
    # in CPS:
    # Comment from Phil Gallespy:
    # 1st byte is MSB, but note that upper two bits are reserved bits.
    # cps_int |= ((uint16_t(cps_char[0]) << 8) & 0x3f00);
    # cps_int |=  (uint16_t(cps_char[1]) & 0x00ff);
    # my observation: highest bit in MSB is always set!
    # e.g.: 80 1C  -> the returned CPS is 28
    # e.g.: FF FF  -> = 3F FF -> the returned maximum CPS is 16383
    #                 or 16383 * 60 = 982980 CPM
    # return CPM even if CPS requested (then return is CPS*60 )

    if CPMflag:
        rec, error, errmessage = serialCOMM(ser, b'<GETCPM>>', 2, orig(__file__))
        vprint(gglobs.verbose, "getCPMS: CPMflag=True, rec=", rec)
        if error == 0 or error == 1:
            rec = rec[0]<< 8 | rec[1]

    else: #CPS
        rec, error, errmessage = serialCOMM(ser, b'<GETCPS>>', 2, orig(__file__))
        vprint(gglobs.verbose, "getCPMS: CPMflag=False, rec=", rec)
        if error == 0 or error == 1:
            rec =  ((rec[0] & 0x3f) << 8 | rec[1]) * 60
        #print "Testing:    len={:}, MSB:{:x}={:d}, LSB:{:x}={:d}, value:{:d} ".format(len(rec), (rec[0]), (rec[0]), (rec[1]), (rec[1]), r)

    return (rec, error, errmessage)


def turnHeartbeatOn(ser):
    # 3. Turn on the GQ GMC heartbeat
    # Note:     This command enable the GQ GMC unit to send count per second data to host every second automatically.
    # Command:  <HEARTBEAT1>>
    # Return:   A 16 bit unsigned integer is returned every second automatically. Each data package consist of 2 bytes data from GQ GMC unit.
    #           The first byte is MSB byte data and second byte is LSB byte data.
    # e.g.:     10 1C     the returned 1 second count is 28.   Only lowest 14 bits are used for the valid data bit.
    #           The highest bit 15 and bit 14 are reserved data bits.
    # Firmware supported:  GMC-280, GMC-300  Re.2.10 or later

    if ser == None: return ("", 1, "No serial connection, returning")

    rec, error, errmessage = serialCOMM(ser, b'<HEARTBEAT1>>', 0, orig(__file__))
    #print (rec, error, errmessage)

    return (rec, error, errmessage)


def turnHeartbeatOFF(ser):
    # 4. Turn off the GQ GMC heartbeat
    # Command:  <HEARTBEAT0>>
    # Return:   None
    # Firmware supported:  Re.2.10 or later

    if ser == None: return ("", 1, "No serial connection, returning")

    rec, error, errmessage = serialCOMM(ser, b'<HEARTBEAT0>>', 0, orig(__file__))
    #print (rec, error, errmessage)

    return (rec, error, errmessage)


def getVOLT(ser):
    # Get battery voltage status
    # send <GETVOLT>> and read 1 byte
    # returns one byte voltage value of battery (X 10V)
    # e.g.: return 62(hex) is 9.8V
    # Example: Geiger counter GMC-300E Plus v4.20
    # with Li-Battery 3.7V, 800mAh (2.96Wh)
    # -> getVOLT reading is: 4.2V
    # -> Digital Volt Meter reading is: 4.18V

    rec, error, errmessage = serialCOMM(ser, b'<GETVOLT>>', 1, orig(__file__))
    dprint(gglobs.debug, "getVOLT:", rec)

    if error == 0 or error == 1:
        rec = rec[0]/10.0

    return (rec, error, errmessage)


def getSPIR(ser, address = 0, datalength = 4096):
    # Request history data from internal flash memory
    # Command:  <SPIR[A2][A1][A0][L1][L0]>>
    # A2,A1,A0 are three bytes address data, from MSB to LSB.
    # The L1,L0 are the data length requested.
    # L1 is high byte of 16 bit integer and L0 is low byte.
    # The length normally not exceed 4096 bytes in each request.
    # Return: The history data in raw byte array.
    # Comment: The minimum address is 0, and maximum address value is
    # the size of the flash memory of the GQ GMC Geiger count. Check the
    # user manual for particular model flash size.

    # address must not exceed 2^(3*8) = 16 777 215 because high byte
    # is clipped off and only lower 3 bytes are used here
    # (but device address is limited to 2^20 - 1 = 1 048 575 = "1M"
    # anyway, or even only 2^16 - 1 = 65 535 = "64K" !)

    # datalength must not exceed 2^16 = 65536 or python conversion
    # fails with error; should be less than 4096 anyway

    # device delivers [(datalength modulo 4096) + 1] bytes,
    # e.g. with datalength = 4128 (= 4096 + 32 = 0x0fff + 0x0020)
    # it returns: (4128 modulo 4096) + 1 = 32 + 1 = 33 bytes

    # This contains a WORKAROUND:
    # it asks for only (datalength - 1) bytes,
    # but then reads one more byte, so the original datalength

    # pack address into 4 bytes, big endian; then clip 1st byte = high byte!
    ad = struct.pack(">I", address)[1:]
    vprint(gglobs.verbose, "SPIR address:", "{:5d}, hex chars in SPIR command: {:02x} {:02x} {:02x}".format(address, ord(ad[0]), ord(ad[1]), ord(ad[2])))

    ###########################################################################
    # BUG ALERT - WORKAROUND
    # pack datalength into 2 bytes, big endian; use all bytes
    # NOTE: this workaround is for "GMC-300E Plus v4.20" and "GMC-320" and perhaps "GMC-500"
    # for GMC-300 v3.20 the '- 1' must be dropped!
    # gglobs.devicesIndex= 3 --> "GMC-300 v3.20"
    if gglobs.devicesIndex == 3:
        dl = struct.pack(">H", datalength)
    else:
        dl = struct.pack(">H", datalength - 1)
    ###########################################################################

    vprint(gglobs.verbose,   "SPIR datalength requested:","{:5d}, hex chars in SPIR command: {:02x} {:02x}".format(datalength, ord(dl[0]), ord(dl[1])))
    dprint(gglobs.debug,     "SPIR requested: address:{:5d}, datalength:{:5d}".format(address, datalength))

    rec = serialCOMM(ser, b'<SPIR'+ad+dl+'>>', datalength, orig(__file__), False) # returns ASCII string

    if rec[0] != None :
        dprint(gglobs.debug, "SPIR received:                 datalength:{:5d}".format(len(rec[0])))
    else:
        dprint(gglobs.debug, "SPIR received:   ERROR: No data received!")

    return rec


def getHeartbeatCPS(ser):
    """read bytes until no further bytes coming"""

    if not gglobs.debug: return  # execute only in debug mode
    eb= 0
    while True:                  # read more until nothing is returned
                                 # (actually, never more than 1 more is returned)
        eb += 1
        rec = ""
        rec = ser.read(2)
        rec = map (ord, rec)
        cps =  ((rec[0] & 0x3f) << 8 | rec[1])
        #print "eb=", eb

        #print "cps:", cps
        """
        if len(x) > 0:
            #dprint(gglobs.debug, "got more bytes: x=", x, ", type:", type(x), ", len(x)=", len(x), ", dec value:", ord(x))
            print "got more bytes: x=", x, ", type:", type(x), ", len(x)=", len(x), ", dec value:"#, ord(x)
            rec += x
        else:
            dprint(gglobs.debug, "no more bytes : x=", x, ", type:", type(x), ", len(x)=", len(x))
            break
        """
        break

    #dprint(gglobs.debug, "read extra {} bytes to total{},".format(len(rec), rec), type(rec))

    return cps


def getExtraByte(ser):
    """read bytes until no further bytes coming"""

    rec = b""
    while True:                  # read single byte until nothing is returned
        x = ser.read(1)
        if len(x) > 0:
            if ord(x) < 128 and ord(x) > 31:
                xu = x
            else:
                xu = "."

            dprint(gglobs.debug, u"getExtraByte: got byte:'{:1s}'    value(dec):{:3d}".format(xu, ord(x)))
            rec += x
        else:
            dprint(gglobs.debug, u"getExtraByte: no more bytes")
            break

    #rec = "test\xff\xff\xff"
    # next rec is cfg from 300E+
    #rec = map(chr, [0, 0, 0, 2, 31, 0, 0, 100, 0, 60, 20, 174, 199, 62, 0, 240, 20, 174, 199, 63, 3, 232, 0, 0, 208, 64, 4, 0, 0, 0, 63, 0, 2, 0, 0, 0, 0, 0, 255, 255, 255, 255, 255, 255, 0, 1, 0, 120, 25, 255, 255, 60, 0, 8, 255, 1, 0, 252, 10, 0, 1, 10, 17, 6, 2, 13, 52, 32, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255, 255])

    recasc = convertBytesToAscii(rec)

    dprint(gglobs.debug, "getExtraByte: Cleaned {} bytes from pipeline:".format(len(rec)), map(ord, rec))
    dprint(gglobs.debug, "getExtraByte: Cleaned bytes as ASCII: '{}'".format(recasc))

    return rec


def getCFG(ser):
    # Get configuration data
    # send <GETCFG>> and read 256 bytes
    # returns the configuration data as a Python list of 256 int

    """
    The meaning is: (from: http://www.gqelectronicsllc.com/forum/topic.asp?TOPIC_ID=4447)

    CFG data Offset table. Start from 0
    ==========================================
    PowerOnOff, //to check if the power is turned on/off intended
    AlarmOnOff, //1
    SpeakerOnOff,
    GraphicModeOnOff,
    BackLightTimeoutSeconds,
    IdleTitleDisplayMode,
    AlarmCPMValueHiByte, //6
    AlarmCPMValueLoByte,
    CalibrationCPMHiByte_0,
    CalibrationCPMLoByte_0,
    CalibrationuSvUcByte3_0,
    CalibrationuSvUcByte2_0, //11
    CalibrationuSvUcByte1_0,
    CalibrationuSvUcByte0_0,
    CalibrationCPMHiByte_1,
    CalibrationCPMLoByte_1, //15
    CalibrationuSvUcByte3_1,
    CalibrationuSvUcByte2_1,
    CalibrationuSvUcByte1_1,
    CalibrationuSvUcByte0_1,
    CalibrationCPMHiByte_2, //20
    CalibrationCPMLoByte_2,
    CalibrationuSvUcByte3_2,
    CalibrationuSvUcByte2_2,
    CalibrationuSvUcByte1_2,
    CalibrationuSvUcByte0_2, //25
    IdleDisplayMode,
    AlarmValueuSvByte3,
    AlarmValueuSvByte2,
    AlarmValueuSvByte1,
    AlarmValueuSvByte0, //30
    AlarmType,
    SaveDataType,
    SwivelDisplay,
    ZoomByte3,
    ZoomByte2, //35
    ZoomByte1,
    ZoomByte0,
    SPI_DataSaveAddress2,
    SPI_DataSaveAddress1,
    SPI_DataSaveAddress0, //40
    SPI_DataReadAddress2,
    SPI_DataReadAddress1,
    SPI_DataReadAddress0,
    PowerSavingMode,
    Reserved, //45
    Reserved,
    Reserved,
    DisplayContrast,
    MAX_CPM_HIBYTE,
    MAX_CPM_LOBYTE, //50
    Reserved,
    LargeFontMode,
    LCDBackLightLevel,
    ReverseDisplayMode,
    MotionDetect, //55
    bBatteryType,
    BaudRate,
    Reserved,
    GraphicDrawingMode,
    LEDOnOff,
    Reserved,
    SaveThresholdValueuSv_m_nCPM_HIBYTE,
    SaveThresholdValueuSv_m_nCPM_LOBYTE,
    SaveThresholdMode,
    SaveThresholdValue3,
    SaveThresholdValue2,
    SaveThresholdValue1,
    SaveThresholdValue0,
    Save_DateTimeStamp, //this one uses 6 byte space
    """

    rec = serialCOMM(ser, b'<GETCFG>>', 256, orig(__file__))
    dprint(gglobs.debug, "getCFG:", rec)

    #
    # Cleaning pipeline - relevant at least for GMC-500
    #
    if gglobs.cleanPipelineFlag  == True:
        dprint(gglobs.debug, "makeHIST: Cleaning pipeline before reading history")
        extra = gcommands.getExtraByte(gglobs.ser)

    #dprint(gglobs.debug, "getCFG:  cfg was read - now cleaning pipeline")
    #extra = getExtraByte(gglobs.ser)

    return rec


def writeConfigData(ser, cfg, cfgaddress, value):
    # 9. Write configuration data
    # Command:  <WCFG[A0][D0]>>
    # A0 is the address and the D0 is the data byte(hex).
    # A0 is offset of byte in configuration data.
    # D0 is the assigned value of the byte.
    # Return: 0xAA
    # Firmware supported: GMC-280, GMC-300 Re.2.10 or later

    #cfg_start = cfg

    # erase config
    rec  = serialCOMM(ser, b'<ECFG>>', 1, orig(__file__))
    #cfg_erased, error, errmessage = getCFG(ser)

    #for i in range(0,255):
    #    if cfg_start[i] != cfg_erased[i]:
    #        print "{:3d} start:{:3d} erased:{:3d}".format(i, cfg_start[i], cfg_erased[i])


    #print "cfg", type(cfg), cfg
    cfg[cfgaddress] = value
    #print "cfgnew", type(cfg), cfg
    cfg = remove_trailing(cfg, remove_value=255)
    #print "cfgclipped", type(cfg), cfg

    for i, c in enumerate(cfg):
        #print i, c, "\t"
        A0 = chr(i)
        D0 = chr(c)
        rec  = serialCOMM(ser, b'<WCFG{}{}>>'.format(A0, D0), 1, orig(__file__))

    rec  = updateConfig(gglobs.ser)
    dprint(gglobs.debug, "writeConfigData:", rec)

    return rec


def updateConfig(ser):
    # 13. Reload/Update/Refresh Configuration
    # Command: <CFGUPDATE>>
    # Return: 0xAA
    # Firmware supported: GMC-280, GMC-300 Re.2.20 or later

    rec  = serialCOMM(ser, b'<CFGUPDATE>>', 1, orig(__file__))
    dprint(gglobs.debug, "updateConfig:", rec)
    return rec


def getSERIAL(ser):
    # Get serial number
    # send <GETSERIAL>> and read 7 bytes
    # returns the serial number in 7 bytes
    # each nibble of 4 bit is a single hex digit of a 14 character serial number
    # e.g.: F488007E051234
    #
    # This routine returns the serial number as a 14 character ASCII string

    rec, error, errmessage  = serialCOMM(ser, b'<GETSERIAL>>', 7, orig(__file__))
    dprint(gglobs.debug, "getSERIAL:", rec)

    if error == 0 or error == 1:  # Ok or Warning
        hexlookup = "0123456789ABCDEF"
        sn =""
        for i in range(0,7):
            n1   = ((rec[i] & 0xF0) >>4)
            n2   = ((rec[i] & 0x0F))
            sn  += hexlookup[n1] + hexlookup[n2]
        rec = sn

    dprint(gglobs.debug, u"getSERIAL: rec={}, error={}, errmessage='{}'".format(rec, error, errmessage))

    return (rec, error, errmessage)


def setDATETIME(ser):
    # from GQ-RFC1201.txt:
    # NOT CORRECT !!!!
    # 22. Set year date and time
    # command: <SETDATETIME[YYMMDDHHMMSS]>>
    # Return: 0xAA
    # Firmware supported: GMC-280, GMC-300 Re.3.00 or later

    # from: GQ-GMC-ICD.odt
    # CORRECT! 6 bytes, no square brackets
    # <SETDATETIME[YY][MM][DD][hh][mm][ss]>>

    tl      = list(time.localtime())
    tl[0]  -= 2000
    tlstr   = b''
    for i in range(0,6):
        tlstr += chr(tl[i])

    rec = serialCOMM(ser, b'<SETDATETIME'+ tlstr +'>>', 1, orig(__file__))
    dprint(gglobs.debug, "setDATETIME:", rec)
    return rec


def getDATETIME(ser):
    # Get year date and time
    # send <GETDATETIME>> and read 7 bytes
    # returns 7 bytes data: YY MM DD HH MM SS 0xAA
    #
    # This routine returns date and time in the format:
    #       YYYY-MM-DD HH:MM:SS
    # e.g.: 2017-12-31 14:03:19

    rec, error, errmessage = serialCOMM(ser, b'<GETDATETIME>>', 7, orig(__file__))
    #rec = [25, 65, 28, 0, 0, 0, 63] # output from GMC-500
    dprint(gglobs.debug, "getDATETIME():", rec, ", len(rec):"+str(len(rec)))

    if error == 0 or error == 1:  # Ok or only Warning
        try:
            rec  = datetime.datetime(rec[0] + 2000, rec[1], rec[2], rec[3], rec[4], rec[5])
        except:
            # conversion to date failed
            rec         = "2099-09-09 09:09:09" # overwrite rec with fake date
            error       = -1
            errmessage  = "ERROR getting Date & Time from device"
            dprint(True, u"getDATETIME(): rec={}, error={}, errmessage='{}'".format(rec, error, errmessage))
            return (rec, error, errmessage)

    dprint(gglobs.debug, u"getDATETIME(): rec={}, error={}, errmessage='{}'".format(rec, error, errmessage))
    return (rec, error, errmessage)


def getTEMP(ser):
    # Get temperature
    # Firmware supported: GMC-320 Re.3.01 or later (NOTE: Not for GMC-300!)
    # send <GETTEMP>> and read 4 bytes
    # Return: Four bytes celsius degree data in hexdecimal: BYTE1,BYTE2,BYTE3,BYTE4
    # Here: BYTE1 is the integer part of the temperature.
    #       BYTE2 is the decimal part of the temperature.
    #       BYTE3 is the negative signe if it is not 0.  If this byte is 0,
    #       then current temperture is greater than 0, otherwise the temperature is below 0.
    #       BYTE4 always 0xAA

    rec, error, errmessage  = serialCOMM(ser, b'<GETTEMP>>', 4, orig(__file__))
    dprint(gglobs.debug, "getTEMP:", rec)

    if error == 0 or error == 1:  # Ok or Warning
        temp = rec[0] + rec[1]/10.0     # unclear: is  decimal part rec[1] single digit or a 2 digit?
                                        # 3 digit not possible as byte value is from 0 ... 255
                                        # expecting rec[1] always from 0 ... 9
        if rec[2] <> 0 : temp *= -1
        if rec[1]  > 9 : temp  = str(temp) + " ERROR: illegal value found for decimal part of temperature ={}".format(rec[1])
        rec = temp

    dprint(gglobs.debug, "getTEMP:", rec)

    return (rec, error, errmessage)


def getGYRO(ser):
    # Get gyroscope data
    # Firmware supported: GMC-320 Re.3.01 or later (NOTE: Not for GMC-300!)
    # Send <GETGYRO>> and read 7 bytes
    # Return: Seven bytes gyroscope data in hexdecimal: BYTE1,BYTE2,BYTE3,BYTE4,BYTE5,BYTE6,BYTE7
    # Here: BYTE1,BYTE2 are the X position data in 16 bits value. The first byte is MSB byte data and second byte is LSB byte data.
    #       BYTE3,BYTE4 are the Y position data in 16 bits value. The first byte is MSB byte data and second byte is LSB byte data.
    #       BYTE5,BYTE6 are the Z position data in 16 bits value. The first byte is MSB byte data and second byte is LSB byte data.
    #       BYTE7 always 0xAA

    rec, error, errmessage  = serialCOMM(ser, b'<GETGYRO>>', 7, orig(__file__))
    dprint(gglobs.debug, "getGYRO:", rec)

    if error == 0 or error == 1:  # Ok or Warning
        x = rec[0] * 256 + rec[1]
        y = rec[2] * 256 + rec[3]
        z = rec[4] * 256 + rec[5]
        rec = (x,y,z)
        rec = "X=0x{:04x}, Y=0x{:04x}, Z=0x{:04x}   ({},{},{})".format(x,y,z,x,y,z)

    dprint(gglobs.debug, "getGYRO:", rec)

    return rec, error, errmessage


def setPOWEROFF(ser):
    # 12. Power OFF
    # Command: <POWEROFF>>
    # Return: none
    # Firmware supported: GMC-280, GMC-300 Re.2.11 or later

    rec  = serialCOMM(ser, b'<POWEROFF>>', 0, orig(__file__))
    dprint(gglobs.debug, "setPOWEROFF:", rec)

    return rec


def setPOWERON(ser):
    # 26. Power ON
    # Command: <POWERON>>
    # Return: none
    # Firmware supported: GMC-280, GMC-300, GMC-320 Re.3.10 or later

    rec  = serialCOMM(ser, b'<POWERON>>', 0, orig(__file__))
    dprint(gglobs.debug, "setPOWERON:", rec)

    return rec


def setREBOOT(ser):
    # 21. Reboot unit
    # command: <REBOOT>>
    # Return: None
    # Firmware supported: GMC-280, GMC-300 Re.3.00 or later

    rec  = serialCOMM(ser, b'<REBOOT>>', 0, orig(__file__))
    dprint(gglobs.debug, "setREBOOT:", rec)

    return rec


def setFACTORYRESET(ser):
    # 20. Reset unit to factory default
    # command: <FACTORYRESET>>
    # Return: 0xAA
    # Firmware supported: GMC-280, GMC-300 Re.3.00 or later

    rec  = serialCOMM(ser, b'<FACTORYRESET>>', 1, orig(__file__))
    dprint(gglobs.debug, "setFACTORYRESET:", rec)

    return rec


#
# Derived commands and functions
#

def isPowerOn(cfg = None):
    """Checks Power On status in the configuration
    Power at offset:0"""

    if cfg == None:
        cfg, error, errmessage = getCFG(gglobs.ser)

    c = cfg[gglobs.cfgOffsetPower]
    if c == 0:
        p = "ON"
    elif c == 255:
        p = "OFF"
    else:
        p = "Unknown (Logging can be started, but if Power OFF will yield 0 only!)"

    return p


def isAlarmOn(cfg = None):
    """Checks Alarm On status in the configuration
    Alarm at offset:1"""

    if cfg == None:
        cfg, error, errmessage = getCFG(gglobs.ser)

    c = cfg[gglobs.cfgOffsetAlarm]
    if c == 0:
        p = "OFF"
    elif c == 1:
        p = "ON"
    else:
        p = "Unknown Alarm Status: {} !".format(c)

    return p


def isSpeakerOn(cfg = None):
    """Checks Speaker On status in the configuration
    Speaker at offset:2"""

    if cfg == None:
        cfg, error, errmessage = getCFG(gglobs.ser)

    c = cfg[gglobs.cfgOffsetSpeaker]
    if c == 0:
        p = "OFF"
    elif c == 1:
        p = "ON"
    else:
        p = "Unknown Speaker Status: {} !".format(c)

    return p


def getSaveDataType(cfg):
    """
    Bytenumber:32  Parameter: CFG_SaveDataType
    0 = off (history is off),
    1 = CPS every second,
    2 = CPM every minute,
    3 = CPM recorded once per hour.
    """

    sdttxt = gglobs.savedatatypes
    #print sdttxt, len(sdttxt)

    sdt    = cfg[gglobs.cfgOffsetSDT]
    #print "sdt:", sdt
    try:
        if sdt <= len(sdttxt):
            txt = sdttxt[sdt]
        else:
            txt = "Unknown SaveDataType: {}".format(sdt)
    except:
        txt= "Error in getSaveDataType, undefined type: {}".format(sdt)

    return sdt, txt


def getBAUDRATE(cfg):
    # reads the baudrate from the configuration data
    # cfg is configuration as returned by getCFG(ser)
    # Note: kind of pointless, because in order to read the config data
    # from the device you must already the baudrate,
    # or the comm will fail :-/
    """
    baudrate = 1200         # config setting:  64
    baudrate = 2400         # config setting: 160
    baudrate = 4800         # config setting: 208
    baudrate = 9600         # config setting: 232
    baudrate = 14400        # config setting: 240
    baudrate = 19200        # config setting: 244
    baudrate = 28800        # config setting: 248
    baudrate = 38400        # config setting: 250
    baudrate = 57600        # config setting: 252
    baudrate = 115200       # config setting: 254
    #baudrate = 921600      # config setting: not available
    """

    brdict = {64:1200, 160:2400, 208:4800, 232:9600, 240:14400, 244:19200, 248:28800, 250:38400, 252:57600, 254:115200}

    #print "cfg      cfg Baudrate"
    #for key, value in sorted(brdict.iteritems()):
    #    print "{:08b} {:3d} {:6d}".format(key, key, value)

    try:
        key = cfg[57]
        rec = brdict[key]
    except:
        rec = "ERROR: Baudrate for cfg[57]={} is unknown".format(key)

    return rec


def autoBAUDRATE(usbport, baudrates):
    """Tries to find a proper baudrate by testing for successful serial
    communication at up to all possible baudrates, beginning with the
    highest
    NOTE: the device port can be opened without error at any baudrate,
    even when no communication can be done, e.g. due to wrong baudrate.
    Therfore we test for successful communication by checking for correct
    number of bytes returned. ON success, this baudrate will be returned.
    A baudrate=0 will be returned when all communication fails.
    On a serial error, a hard exit will occur.
    """

    vprint(True, "Autodiscovery of baudrate")
    baudrates.sort(reverse=True) # to start with highest baudrate
    foundit = False
    for baudrate in baudrates:
        vprint(True, "Trying baudrate:", baudrate)
        try:
            ser = serial.Serial(usbport, baudrate, timeout= 1)
            ser.write(b'<GETVER>>')
            rec = ser.read(14)
            ser.close()
            if len(rec) == 14:
                foundit = True
                vprint(True, "Success with {}".format(baudrate))
                break
        except:
            vprint(True, "ERROR Serial communication error when trying to find baudrate:", sys.exc_info())
            fprint("ERROR Serial communication error when trying to find baudrate")
            return None

    return baudrate if foundit else 0


def autoPORT(usbport, baudrates):
    """Tries to find a working port and baudrate by testing all serial
    ports for successful communication by auto discovery of baudrate.
    All available ports will be listed with the highest baudrate found.
    The program will exit and a restart with port and baudrate as found
    isrequired
    """

    vprint(True, "Autodiscovery of Serial Ports")

    time.sleep(0.5) # a freshly plugged in device, not fully recognized
                    # by system, sometimes produces errors

    ports =[]
    lp = serial.tools.list_ports.comports()

    if len(lp) == 0:
        errmessage = "ERROR: No available serial ports found"
        dprint(True, errmessage)
        return None, errmessage

    else:
        vprint(True, "Found these ports:")
        for p in lp :
            vprint(True, p)
            ports.append(str(p).split(" ",1)[0])
        vprint(True, "")

    ports.sort()
    ports_found = []

    vprint(True, "Testing all ports for communication:")
    for port in ports:
        vprint(True, "Port:", port)
        abr = autoBAUDRATE(port, baudrates)
        if abr > 0:
            ports_found.append((port, abr))
        elif abr == 0:
            vprint(True, "Failure - no communication at any baudrate")
        else:
            return None, "ERROR: Failure during Serial Communication"

    if len(ports_found) == 0:
        errmessage = "ERROR: No communication at any serial port and baudrate"
        dprint(True, errmessage)
        return None, errmessage

    return ports_found, ""


#
# Communication with serial port with exception handling
#

def serialCOMM(ser, sendtxt, returnlength, caller = ("", -1), byteformat = True):
    # write to and read from serial port, exit on serial port error
    # when not enough bytes returned, try send+read again up to 5 times.
    # exit if it still fails
    # if byteformat is True, then convert string to list of int
    # before returning the record

    #fprint("Caller is: {} in line no:{}".format(caller[0], caller[1]),"")

    rec     = None
    error   = 0
    errmessage = ""

    if ser == None:
        return ( "", -1, "Serial Port is closed")

    time.sleep(0.03)  # occasional failures, when it goes too fast

    try:
        ser.write(sendtxt)
    except:
        dprint(True, "serialCOMM: ERROR: WRITE failed in function serialCOMM")
        dprint(True, "serialCOMM: ERROR: sys.exc_info(): ", sys.exc_info())
        dprint(True, "serialCOMM: ERROR: caller is: {} in line no:{}".format(caller[0], caller[1]))
        dprint(True, traceback.format_exc())
        try:
            ser.close()
        except:
            pass

        error   = -1
        errmessage = "serialCOMM: ERROR: WRITE failed in function serialCOMM. See log for details"
        return (rec, error, errmessage)

    time.sleep(0.03)

    try:
        rec = ser.read(returnlength)
    except:
        dprint(True, "serialCOMM: ERROR: READ failed in function serialCOMM")
        dprint(True, "serialCOMM: ERROR: sys.exc_info(): ", sys.exc_info())
        dprint(True, "serialCOMM: ERROR: caller is: {} in line no:{}".format(caller[0], caller[1]))
        dprint(True, traceback.format_exc())
        try:
            ser.close()
        except:
            pass

        error   = -1
        errmessage = "serialCOMM: ERROR: READ failed in function serialCOMM. See log for details"
        return (rec, error, errmessage)

    if len(rec) < returnlength:
        fprint("Found a device but got ERROR communicating via serial port. Retrying")
        dprint(True, "ERROR: in serialCOMM: Received length:{} is less than requested:{}".format(len(rec), returnlength))

        error    = 1
        errmessage  = "serialCOMM: ERROR: Record too short: Received bytes:{} < requested:{}".format(len(rec), returnlength)

        # RETRYING
        count    = 1
        countmax = 5
        while True:
            beep()
            dprint(True, "serialCOMM: RETRY: to get full return record, trial #", count)
            fprint("serialCOMM: ERROR communicating via serial port. Retrying again.")

            time.sleep(1)
            ser.write(sendtxt)

            time.sleep(0.3)
            rec = ser.read(returnlength)

            if len(rec) == returnlength:
                dprint(True, "serialCOMM: RETRY: returnlength is {} bytes. OK now. Continuing normal cycle".format(len(rec)))
                errmessage += "; ok after {} retry".format(count)
                break
            else:
                dprint(True, "serialCOMM: RETRY: returnlength is {} bytes. Still NOT ok; trying again".format(len(rec)))

            count += 1
            if count >= countmax:
                dprint(True, "serialCOMM: RETRY: Tried {} times, always failure, giving up".format(count))
                dprint(True, "serialCOMM: ERROR: Serial communication error. Is the baudrate set correctly?")
                error = -1
                #errmessage += "; still too short after {} retries".format(countmax)
                errmessage = "serialCOMM: ERROR communicating  - giving up - is the baudrate set correctly?"
                return (None, error, errmessage)

    if byteformat: rec = map(ord,rec) # convert string to list of int

    return (rec, error, errmessage)


def serialOPEN(usbport, baudrate, timeout):
    """Tries to open the serial port
    Return: on success: ser, ""
            on failure: None, errmessage
    """

    cfg         = ""
    error       = 0
    errmessage  = "unknown error"
    try:
        gglobs.ser = serial.Serial(usbport, baudrate, timeout=timeout)
        # ser is like: Serial<id=0x7f2014d371d0, open=True>(port='/dev/gqgmc', baudrate=115200, bytesize=8, parity='N', stopbits=1, timeout=20, xonxoff=False, rtscts=False, dsrdtr=False)
    except serial.SerialException as e:
        errmessage1  = "serialOPEN: ERROR: {}".format(e.strerror)
        errmessage2  = "serialOPEN: ERROR: settings tried: port='{}', baudrate={}, timeout={}".format(usbport, baudrate, timeout)
        dprint(True, errmessage1)
        dprint(True, errmessage2)

        return None, "{}\n{}".format(errmessage1, errmessage2)

    dprint(gglobs.debug, "serialOPEN: Serial port successfully opened")

    # NOTE: the device port can be opened without error even when no
    # communication can be done, e.g. due to wrong baudrate
    # This tests for successful communication
    try:
        cfg, error, errmessage = getCFG(gglobs.ser)
        #print "cfg, error, errmessage", cfg, error, errmessage
    except:
        errmessage1  = "serialOPEN: ERROR: communication with device failed. Baudrate correct?"
        errmessage2  = "serialOPEN: ERROR: settings tried: port='{}', baudrate={}, timeout={}".format(usbport, baudrate, timeout)
        dprint(True, errmessage)
        dprint(True, errmessage1)
        dprint(True, errmessage2)

        return None, "{}\n{}\n{}".format(errmessage, errmessage1, errmessage2)

    if error < 0:
        dprint(True, "serialOPEN: ERROR: Communication problem with device:", errmessage)
        return None, errmessage


    #gglobs.powerstate = "ON" if isPowerOn(cfg) else "OFF"
    gglobs.powerstate = isPowerOn(cfg)

    dprint(gglobs.debug, "serialOPEN: Serial communication successful with device at serial port: '{}', baudrate: {}, timeout: {} sec".format(gglobs.ser.name, gglobs.ser.baudrate, gglobs.ser.timeout))
    dprint(gglobs.debug, "serialOPEN: Powerstate of device is: {}".format(gglobs.powerstate))

    return gglobs.ser, ""


def ftextDeviceInfo():
    """Return device info as formatted text"""

    dprint(gglobs.debug, "ftextDeviceInfo: begin ------------------------------")

    while True:

        pText  = header("Device Info") + "\n"
        pText = pText.decode('utf-8')

        cfg, error, errmessage     = getCFG(gglobs.ser)
        if error < 0:
            pText += errmessage
            #return pText
            break

        # device name
        pText += "{:35s} {}\n".format("Selected device:", gglobs.device)


        # firmware version number
        ver, error, errmessage = getVER(gglobs.ser)
        if error < 0:
            pText += errmessage
            #return pText
            break
        else:
            try:
                pText  += u"{:35s} {}\n".format("Device Firmware Version:",  ver)
            except:
                # ver is not in ASCII format
                errmessage  = "ERROR getting Firmware Version from device"
                pText  += u"{:35s} {}\n".format("Device Firmware Version:",  errmessage)
                dprint(True, errmessage, ", not ASCII - got:", map(ord,ver))

        #clean
        #extra = getExtraByte(gglobs.ser)

        # serial number
        sn, error, errmessage = getSERIAL(gglobs.ser)
        if error < 0:
            pText += errmessage
            #return pText
            break
        else:
            pass
            pText  += u"{:35s} {}\n".format("Device serial number:",     sn)


        #clean
        #extra = getExtraByte(gglobs.ser)

        # connected port
        pText  += u"{:35s} {} (Timeout: {} sec)\n".format("Device connected with port:",  gglobs.usbport, gglobs.timeout)

        # baudrate as read from device
        pText  += u"{:35s} {}\n".format("Baudrate read from device:",  getBAUDRATE(cfg))


        #clean
        #extra = getExtraByte(gglobs.ser)

        # baudrate as set in program
        pText  += u"{:35s} {}\n".format("Baudrate set by program:",  gglobs.baudrate)

        # get date and time from device, compare with computer time
        rec, error, errmessage = getDATETIME(gglobs.ser)
        if error < 0:
            pText += u"{:35s} {}\n".format("Date and Time from device:", errmessage)
            #return pText
        else:
            devtime = str(rec)
            cmptime = stime()
            deltat  = datestr2num(cmptime) - datestr2num(devtime)
            if deltat == 0:
                dtxt = "Device time is same as computer time"
            elif deltat > 0:
                dtxt = "Device is slower than computer by {:0.0f} sec".format(deltat)
            else:
                dtxt = "Device is faster than computer by {:0.0f} sec".format(abs(deltat))
            pText  += "{:35s} {}\n".format("Date and Time from device:", devtime)
            pText  += "{:35s} {}\n".format("Date and Time from computer:", cmptime)
            pText  += "{:35s} {}\n".format("", dtxt)

            dprint(True, "ftextDeviceInfo: Date and Time from device is:", devtime)
            dprint(True, "ftextDeviceInfo: Date and Time from computer is:", "{}, {}".format(cmptime, dtxt))

        #clean
        #extra = getExtraByte(gglobs.ser)

        # voltage
        rec, error, errmessage = getVOLT(gglobs.ser)
        if error < 0:
            pText += errmessage
            #return pText
            break
        else:
            pText  += "{:35s} {}\n".format("Device Battery Voltage:", "{} V".format(rec))

        #clean
        #extra = getExtraByte(gglobs.ser)

        # temperature
        rec, error, errmessage = getTEMP(gglobs.ser)
        if error < 0:
            pText += errmessage
            #return pText
            break
        else:
            pText  += u"{:35s} {}\n".format("Device Temperature:", "{} DEG C".format(rec ))
            pText  += u"{:35s} {}\n".format("", "(only GMC-320 Re.3.01 and later)")


        #clean
        #extra = getExtraByte(gglobs.ser)

        # gyro
        rec, error, errmessage = getGYRO(gglobs.ser)
        if error < 0:
            pText += errmessage
            #return pText
            break
        else:
            pText  += u"{:35s} {}\n".format("Device Gyro data:", rec)
            pText  += u"{:35s} {}\n".format("", "(only GMC-320 Re.3.01 and later)")

        #clean
        #extra = getExtraByte(gglobs.ser)

        # power state
        pText      += u"{:35s} {}\n".format("Device Power State:", isPowerOn(cfg))

        # Alarm state
        pText      += u"{:35s} {}\n".format("Device Alarm State:", isAlarmOn(cfg))

        # Speaker state
        pText      += u"{:35s} {}\n".format("Device Speaker State:", isSpeakerOn(cfg))


        # Save Data Type
        sdt, sdttxt = getSaveDataType(cfg)
        pText      += u"{:35s} {}\n".format("Device Save Mode:", sdttxt)

        # MaxCPM
        value = cfg[gglobs.cfgOffsetMaxCPM] * 256 + cfg[gglobs.cfgOffsetMaxCPM +1]
        pText      += u"{:35s} {}\n".format("Max CPM (invalid if 65535!):", value)

        # Calibration
        pText      += ftextCalibration(cfg)

        break

    #dprint(gglobs.debug, pText)

    return pText


def fprintDeviceInfo():
    """Print device info via fprint"""

    dprint(gglobs.debug, u"fprintDeviceInfo: begin ------------------------------")

    forcedebug = "debug"
    while True:

        fprint(header(u"Device Info"))

        cfg, error, errmessage     = getCFG(gglobs.ser)
        #if 1 or error < 0:
        if error < 0:
            fprint(u"ERROR trying to read Device Configuration: '{}'".format(errmessage), forcedebug)
            #break

        # device name
        fprint(u"Selected device:", gglobs.device)

        # firmware version number
        ver, error, errmessage = getVER(gglobs.ser)
        #if 1 or error < 0:
        if error < 0:
            fprint(u"ERROR getting Device Firmware Version: '{}'".format(errmessage), forcedebug)
            #break
        else:
            try:
                fprint(u"Device Firmware Version:",  ver)
            except:
                # ver is not in ASCII format
                errmessage  = "ERROR getting Device Firmware Version; not ASCII - got:" + str( map(ord,ver))
                fprint(errmessage, forcedebug)

        # serial number
        sn, error, errmessage = getSERIAL(gglobs.ser)
        if error < 0:
            fprint(u"ERROR getting Device Serial Number: '{}'".format(errmessage), forcedebug)
            #break
        else:
            #fprint(u"Device Serial Number:",     sn)
            pass

        # connected port
        fprint(u"Device connected with port:", u"{} (Timeout:{} sec)".format(gglobs.usbport, gglobs.timeout))

        # baudrate as read from device
        fprint(u"Baudrate read from device:", getBAUDRATE(cfg))

        # baudrate as set in program
        fprint(u"Baudrate set by program:",  gglobs.baudrate)

        # get date and time from device, compare with computer time
        rec, error, errmessage = getDATETIME(gglobs.ser)
        if error < 0:
            fprint(u"ERROR getting Device Date and Time: '{}'".format(errmessage), forcedebug)
        else:
            devtime = str(rec)
            cmptime = stime()
            deltat  = datestr2num(cmptime) - datestr2num(devtime)
            if deltat == 0:
                dtxt = "Device time is same as computer time"
            elif deltat > 0:
                dtxt = "Device is slower than computer by {:0.0f} sec".format(deltat)
            else:
                dtxt = "Device is faster than computer by {:0.0f} sec".format(abs(deltat))

            fprint("Date and Time from device:", devtime, forcedebug)
            fprint("Date and Time from computer:", cmptime, forcedebug)
            fprint("", dtxt)

        # voltage
        rec, error, errmessage = getVOLT(gglobs.ser)
        if error < 0:
            fprint(u"ERROR getting Device Battery Voltage: '{}'".format(errmessage), forcedebug)
            #break
        else:
            fprint("Device Battery Voltage:", "{} V".format(rec))

        # temperature
        rec, error, errmessage = getTEMP(gglobs.ser)
        if error < 0:
            fprint(u"ERROR getting Device Temperature: '{}'".format(errmessage), forcedebug)
            #break
        else:
            fprint(u"Device Temperature:", "{} DEG C".format(rec ))
            fprint(u"", "(only GMC-320 Re.3.01 and later)")

        # gyro
        rec, error, errmessage = getGYRO(gglobs.ser)
        if error < 0:
            fprint(u"ERROR getting Device Gyro Data: '{}'".format(errmessage), forcedebug)
            #break
        else:
            fprint(u"Device Gyro data:", rec)
            fprint(u"", "(only GMC-320 Re.3.01 and later)")

        # power state
        fprint(u"Device Power State:", isPowerOn(cfg))

        # Alarm state
        fprint(u"Device Alarm State:", isAlarmOn(cfg))

        # Speaker state
        fprint(u"Device Speaker State:", isSpeakerOn(cfg))

        # Save Data Type
        sdt, sdttxt = getSaveDataType(cfg)
        fprint(u"Device Save Mode:", sdttxt)

        # MaxCPM
        value = cfg[gglobs.cfgOffsetMaxCPM] * 256 + cfg[gglobs.cfgOffsetMaxCPM +1]
        fprint(u"Max CPM (invalid if 65535!):", value)

        # Calibration
        fprint(ftextCalibration(cfg), forcedebug)

        break


def ftextCFG():
    """Return device configuration as formatted text"""

    dprint(gglobs.debug, "ftextCFG: begin ------------------------------------")

    fText = header("Device Configuration")

    cfg, error, errmessage = getCFG(gglobs.ser)
    if error < 0:
        fText += errmessage
    else:
        fText += "\nThe configuration is:  (Format: dec byte_number: hex value=dec value)\n"

        while cfg[-1] == 255:  cfg.pop()  # remove trailing FF
        l_pop = len(cfg)
        #l_pop = 256
        for i in range(0, l_pop, 6):
            pcfg = ""
            for j in range(0, 6):
                k = i+j
                if k < l_pop: pcfg += "%3d:%02x=%3d |" % (k, cfg[k], cfg[k])
            fText += pcfg[:-2] + "\n"
        if l_pop < 256:
            fText += "Remaining values up to address 255 are all ff=255"
        else:
            fText += pText[:-1] # remove last newline char

        asc = convertBytesToAscii(map(chr, cfg))
        fText += "\nThe configuration as ASCII is (non-ASCII characters as '.'):\n" + asc

    dprint(gglobs.debug, fText)

    return unicode(fText)


def ftextCalibration(cfg):
    """extract Calibration from device"""

    try:
        cal_CPM = []
        cal_CPM.append(struct.unpack(">H", chr(cfg[8] ) + chr(cfg[9] ) )[0])
        cal_CPM.append(struct.unpack(">H", chr(cfg[14]) + chr(cfg[15]) )[0])
        cal_CPM.append(struct.unpack(">H", chr(cfg[20]) + chr(cfg[21]) )[0])

        #gglobs.devicesIndex = 2 --> u"GMC-500":
        if gglobs.devicesIndex == 2:
            #print "using 500er, use big-endian"
            fString = ">f"
        else:
            #print "using other than 500er, use little-endian"
            fString = "<f"

        cal_uSv = []
        cal_uSv.append(struct.unpack(fString,  chr(cfg[10] ) + chr(cfg[11]) + chr(cfg[12]) + chr(cfg[13]) )[0])
        cal_uSv.append(struct.unpack(fString,  chr(cfg[16] ) + chr(cfg[17]) + chr(cfg[18]) + chr(cfg[19]) )[0])
        cal_uSv.append(struct.unpack(fString,  chr(cfg[22] ) + chr(cfg[23]) + chr(cfg[24]) + chr(cfg[25]) )[0])

        #print cal_CPM
        #print cal_uSv

        ftext = u"Device Calibration:\n"
        for i in range(0,3):
            ftext += u"{:35s}{:6d} CPM = {:6.2f} µSv/h  ({:0.4f} µSv/h / CPM)\n".format(u"   Calibration Point {:}:".format(i + 1), cal_CPM[i], cal_uSv[i], cal_uSv[i] / cal_CPM[i])
        #print "ftextCalibration:", ftext[:-1], type(ftext[:-1])
    except:
        ftext = u"ERROR in getting Calibration\n"

    return ftext[:-1] # remove last newline char



