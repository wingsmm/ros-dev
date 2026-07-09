# Unitree Lidar SDK - win64

## Install

First, install the package.

## Publish

Once the installation is complete, open the sender program located in the "bin" folder of the installation path. The default path is C:\Program Files\unitree_lidar_sdk 1.0.10\bin\unilidar_publisher_udp.exe.

After opening the program, a command prompt window will appear. Please first confirm the serial port number currently used by the radar and enter it in uppercase. For example, enter "COM1" and press Enter to confirm. Finally, fill in the sender port and target IP. For example, if using the local machine, you can enter "127.0.0.1" for the IP address. Please use an available UDP port number for the port, such as "12345".Then, the radar data will be sent.

## Subscrib

Method 1: To obtain radar data by directly listening to the specified IP and port, you can use the receiver program located in the same directory. The path is bin/unilidar_subscriber_udp.exe. You can use this program to validate and receive the radar data.

Method 2: To retrieve radar data using a Python script, you can use the example script located at examples/unilidar_subscriber_udp.py.