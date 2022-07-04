#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later

import dbus
from gi.repository import GLib
import sys
from time import sleep
from dbus.mainloop.glib import DBusGMainLoop
from struct import unpack
import bluezutils
import datetime

bus = None
mainloop = None
adapter = None

BLUEZ_SVC =       'org.bluez'
DBUS_OM_IFACE =   'org.freedesktop.DBus.ObjectManager'
DBUS_PROP_IFACE = 'org.freedesktop.DBus.Properties'
BLUEZ_DEV_IFACE = 'org.bluez.Device1'
GATT_SVC_IFACE =  'org.bluez.GattService1'
GATT_CHRC_IFACE = 'org.bluez.GattCharacteristic1'

DEVICE_NAME =         "Meteodata"
SVC_TEMPSENSOR_UUID = "f553e510-5dc3-409e-858a-98b69a4f2e2b"
CHRC_METEODATA_UUID = "f553e511-5dc3-409e-858a-98b69a4f2e2b"
CHRC_METEODATA_FMT =  "hBBBB"

# The objects that we interact with.
tempsensor_service = None
meteodata_chrc = None


# Dictionnary: key is a tuple (identifier, channel, unit)
# value is a tuple (temperature, humidity, timestamp)
meteodata = {}

def generic_error_cb(error):
    print('D-Bus call failed: ' + str(error))
    mainloop.quit()


def meteodata_start_notify_cb():
    print('Meteodata notifications enabled')

prop_iface_sig = None
def meteodata_changed_cb(iface, changed_props, invalidated_props):
    date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
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
    print(meteodata)


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


def main():
    # Set up the main loop.
    DBusGMainLoop(set_as_default=True)
    global bus
    bus = dbus.SystemBus()
    global mainloop
    mainloop = GLib.MainLoop()
    global adapter
    adapter = bluezutils.find_adapter()
    start_discovery()
    
    while(True):
        print('Getting objects...')
        om = dbus.Interface(bus.get_object(BLUEZ_SVC, '/'), DBUS_OM_IFACE)
        om.connect_to_signal('InterfacesRemoved', interfaces_removed_cb)
        objects = om.GetManagedObjects()
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
