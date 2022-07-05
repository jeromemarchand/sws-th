#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later

import dbus
from gi.repository import GLib
import sys
from time import sleep
from dbus.mainloop.glib import DBusGMainLoop
from struct import unpack
import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

bus = None
mainloop = None
adapter = None

BLUEZ_SVC =       'org.bluez'
DBUS_OM_IFACE =   'org.freedesktop.DBus.ObjectManager'
DBUS_PROP_IFACE = 'org.freedesktop.DBus.Properties'
BLUEZ_ADP_IFACE = 'org.bluez.Adapter1'
BLUEZ_DEV_IFACE = 'org.bluez.Device1'
GATT_SVC_IFACE =  'org.bluez.GattService1'
GATT_CHRC_IFACE = 'org.bluez.GattCharacteristic1'

DEVICE_NAME =         "Meteodata"
SVC_TEMPSENSOR_UUID = "f553e510-5dc3-409e-858a-98b69a4f2e2b"
CHRC_METEODATA_UUID = "f553e511-5dc3-409e-858a-98b69a4f2e2b"
CHRC_METEODATA_FMT =  "hBBBB"
DATE_FMT =            "%Y-%m-%d %H:%M"

# The objects that we interact with.
tempsensor_service = None
meteodata_chrc = None

# Output file
ofile = None

# Dictionnary: key is a tuple (identifier, channel, unit)
# value is a tuple (temperature, humidity, timestamp)
meteodata = {}

def get_managed_objects():
    bus = dbus.SystemBus()
    manager = dbus.Interface(bus.get_object(BLUEZ_SVC, "/"), DBUS_OM_IFACE)
    return manager.GetManagedObjects()


def find_adapter():
    return find_adapter_in_objects(get_managed_objects())


def find_adapter_in_objects(objects):
    bus = dbus.SystemBus()
    for path, ifaces in objects.items():
        adapter = ifaces.get(BLUEZ_ADP_IFACE)
        if adapter is None:
            continue
        obj = bus.get_object(BLUEZ_SVC, path)
        return dbus.Interface(obj, BLUEZ_ADP_IFACE)
    raise Exception("Bluetooth adapter not found")


def generic_error_cb(error):
    print('D-Bus call failed: ' + str(error))
    mainloop.quit()


def meteodata_start_notify_cb():
    print('Meteodata notifications enabled')

prop_iface_sig = None
def meteodata_changed_cb(iface, changed_props, invalidated_props):
    date = datetime.datetime.now()
    if iface != GATT_CHRC_IFACE:
        print("Wrong iface:")
        print(iface)
        return

    if not len(changed_props):
        print("No changed_props")
        return

    value = changed_props.get('Value', None)
    if not value:
        print("No value")
        return

    bvalue = bytes(value)
    entry = unpack(CHRC_METEODATA_FMT, bvalue)
    if entry[4] == 1:
        tunit = "F"
    else:
        tunit = "C"
    print("Sensor ", entry[1], " channel ", entry[2], " : ",
          entry[0]/10, tunit, entry[3], "%")
    meteodata[(entry[1],entry[2],entry[4])] = (entry[0]/10, entry[3], date)
    #print(meteodata)


def start_client():
    global prop_iface_sig
    # Listen to PropertiesChanged signals from the Heart Measurement
    # Characteristic.
    print("Connect to changed properties:")
    prop_iface = dbus.Interface(meteodata_chrc[0], DBUS_PROP_IFACE)
    prop_iface_sig = prop_iface.connect_to_signal("PropertiesChanged",
                                                  meteodata_changed_cb)

    # Subscribe to Heart Rate Measurement notifications.
    print("Start notifications:")
    meteodata_chrc[0].StartNotify(reply_handler=meteodata_start_notify_cb,
                                    error_handler=generic_error_cb,
                                    dbus_interface=GATT_CHRC_IFACE)


def stop_client():
    prop_iface_sig.remove()


def clear_svc_and_chrc():
    global tempsensor_service
    global meteodata_chrc
    tempsensor_service = None
    meteodata_chrc = None


def process_chrc(chrc_path):
    chrc = bus.get_object(BLUEZ_SVC, chrc_path)
    chrc_props = chrc.GetAll(GATT_CHRC_IFACE,
                             dbus_interface=DBUS_PROP_IFACE)

    uuid = chrc_props['UUID']

    if uuid == CHRC_METEODATA_UUID:
        print('Meteodata characteristic found' + chrc_path);
        global meteodata_chrc
        meteodata_chrc = (chrc, chrc_props)
    else:
        print('Unrecognized characteristic: ' + uuid)

    return True


def process_ts_service(service_path, chrc_paths):
    service = bus.get_object(BLUEZ_SVC, service_path)
    service_props = service.GetAll(GATT_SVC_IFACE,
                                   dbus_interface=DBUS_PROP_IFACE)

    uuid = service_props['UUID']

    if uuid != SVC_TEMPSENSOR_UUID:
        return False

    stop_discovery()
    print('TempSensor Service found: ' + service_path)

    # Process the characteristics.
    for chrc_path in chrc_paths:
        process_chrc(chrc_path)

    global tempsensor_service
    tempsensor_service = (service, service_props, service_path)

    return True


def interfaces_removed_cb(object_path, interfaces):
    if not tempsensor_service:
        return

    if object_path == tempsensor_service[2]:
        print('Service was removed')
        stop_client()
        clear_svc_and_chrc()
        mainloop.quit()


def start_discovery():
    print("Start discovery:")
    #scan_filter = { "UUIDs": SVC_TEMPSENSOR_UUID }
    scan_filter = {}
    adapter.SetDiscoveryFilter(scan_filter)
    adapter.StartDiscovery()


def stop_discovery():
    print("Stop discovery:")
    adapter.StopDiscovery()


def convertFtoC(temp):
    return round((temp - 32) / 1.8, 1);


def update_data():
    date = datetime.datetime.now()
    print("Regular update: " + date.strftime(DATE_FMT))
    print(meteodata)
    for key, value in meteodata.items():
        # Ignore outdated data
        if date - value[2] < datetime.timedelta(minutes=5):
            fahrenheit = key[2]
            # Use celsius data when available, fahrenheit otherwise
            if (fahrenheit == 0 or
                ((key[0], key[1], 0) not in meteodata.keys())):
                temp = value[0]
                if fahrenheit == 1:
                    temp = convertFtoC(temp)
                ofile.write(date.strftime(DATE_FMT) +
                            f"{key[0]:4} {key[1]} {temp:8}C {value[1]}%\n")

def usage():
    print(f"Usage: {sys.argv[0]} output_file")

def main():
    if (len(sys.argv) != 2 ):
        usage()
        sys.exit()
    global ofile
    ofile = open(sys.argv[1], 'a', encoding="utf-8", buffering=1)
    ofile.write("# Meteodata: " +
                datetime.datetime.now().strftime(DATE_FMT) + "\n")

    scheduler = BackgroundScheduler()
    scheduler.start()

    trigger = CronTrigger(year="*", month="*", day="*",
                          hour="*", minute="*/15", second="0")
    scheduler.add_job(update_data, trigger=trigger)

    # Set up the main loop.
    DBusGMainLoop(set_as_default=True)
    global bus
    bus = dbus.SystemBus()
    global mainloop
    mainloop = GLib.MainLoop()
    global adapter
    adapter = find_adapter()
    start_discovery()

    while(True):
        print('Getting objects...')
        objects = get_managed_objects()
        chrcs = []
        
        for path, interfaces in objects.items():
            if "org.bluez.Device1" not in interfaces:
                continue
            prop = interfaces[BLUEZ_DEV_IFACE]
            print("%s %s" % (prop["Address"], prop["Alias"]))
            if (prop["Alias"] == DEVICE_NAME):
                address = prop["Address"]
                print("Found Device: " + path, address)
                dev = dbus.Interface(bus.get_object(BLUEZ_SVC, path), BLUEZ_DEV_IFACE)
                dev.Connect()
                print("Connected");
                break

        # List characteristics found
        for path, interfaces in objects.items():
            #print("CHRC:" + path)
            #print(interfaces.keys())
            if GATT_CHRC_IFACE not in interfaces.keys():
                continue
            #print("Add path: " + path);
            chrcs.append(path)

        # List services found
        for path, interfaces in objects.items():
            #print("SVC:" + path);
            if GATT_SVC_IFACE not in interfaces.keys():
                continue

            chrc_paths = [d for d in chrcs if d.startswith(path + "/")]

            if process_ts_service(path, chrc_paths):
                break

        if not tempsensor_service:
            print('No TempSensor Service found')
            clear_svc_and_chrc()
            sleep(10)
            continue

        start_client()

        mainloop.run()
        start_discovery()
        sleep(10)


if __name__ == '__main__':
    main()
