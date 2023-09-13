from importlib import util
import asyncio
from pickle import TRUE
from nio import (AsyncClient, SyncResponse, RoomMessageText)
import asyncio
import asyncio_mqtt as aiomqtt

import paho.mqtt.client as mqtt
from random import randrange, uniform, randint as random
import time
import json

from configparser import ConfigParser


# hardcoded mqtt and infrafon stuff DO NOT TOUCH!
mqttPort = 1883
mqttUrl = "infrafon.cloud" 

mqttUsername = "lukas_dev"
mqttPassword = "Welcome0!"
deviceId = "240ac4ba0490"
backupId = "240ac40a8c80"
deviceIdShort = "0490"
backupIdShort = "8c80"  
mqttEntity = "DemoEntity"
dataviewName = "pharmacy_quest"
app = {
  "buzzer": "dev",
  "message": "pharmacy_quest"
}
# dict for mqtt topics
topic = {
    "buzzer" : f"ife-int/device/msgs-down/{deviceId}",
    "publish" : f"ife/{mqttEntity}/device/app-down/{app['message']}/{deviceId}",
    "subscribe" : f"ife/{mqttEntity}/device/app-up/#",
    "access" : f"ife-int/device/msgs-down/{deviceId}"
}

# dict for matrix keywords
matrixKeywords = {
    "buzzer": "buzz",
    "publish": "infrafon",
    "grant": "grant access",
    "revoke": "revoke access"
}

# stack to handle incoming messages
lastMessages = []
# stack to handle messages that need to be published in matrix
matrixMessagesToBePublished = []
# keeps track of how many messages have been send - 1 because the first message cant be deleted
# so there is a fake dev message to hide that -> messageCounter 1 from the getgo
messageCounter = 1

# hardcoded room_id
hard_coded_room_id = "!aQOXMJarEYHSlTdlKs:freiburg.social"

# array(list) to match the content of the message to their id
contentArray = []
# append the dev message
contentArray.append("Grant access to the Demo-Door?")

# config parser for file management
config = ConfigParser()
config.read("config.ini")

# device list, which should be updated for every new entry or at a certain time frame
localDeviceList = []


async def updateLocalDeviceList(updateLocalDeviceListEvent, loop):
    '''
    Get a device list from the config.ini file, this is used for managing multiple devices and easy 
    addition for new devices. Returns a list with all the device ID's
    '''
    await updateLocalDeviceListEvent.wait()
    try:
        configDeviceList = config.items("device_list")
        
    except:
        print("Error, couldn't access the device_list in the config file!")
        # return empty list to avoid null pointer errors
        return
    
    localDeviceList.clear
    for key, path in configDeviceList:
        localDeviceList.append(path)

    updateLocalDeviceListEvent.clear()
    # publishMessageInMatrixEvent.set() set another event if needed
    loop.create_task(updateLocalDeviceList(updateLocalDeviceListEvent, loop))
    print(localDeviceList)
     


def getCurrentTime():
    '''
    Returns the current time as hour:minute, e.g. 14:10
    '''
    # time object like ''Thu Apr 20 15:10 2023''
    currentTime = time.strftime("%a %b %d %H:%M %Y", time.localtime())
    # split into pieces at ' ' to extract only 15:10
    currentTime = currentTime.split()
    currentTime = currentTime[3]
    return currentTime


# JSON data to activate the buzzer in the infrafon
buzzer_data_json = '{"app": {"dev": {"buzzer": {"song": "V101Z910V201Z910"},"vibration": {"song": "V10S01V10S01"}}}}'
# JSON data to (de)activate the passive nfc antenna
nfc_mqtt_data_grant_json = json.dumps({"app": {"dev": {"passive_nfc": "true"}}})
nfc_mqtt_data_revoke_json = json.dumps({"app": {"dev": {"passive_nfc": "false"}}})


def tupelToInfrafonMessageHelperFunc(data):
    '''
    Helper function for the convertMapToInfrafonMessageFormat
    function.
    '''
    messageData = { 
    "data": {
         "msglist" : [
    {       "id":f"{messageCounter}", # messageId
            "at":getCurrentTime(), # messageTime
            "from": "Frieder", # callNumber
            "subj": data[0], # messageSubject
            "text": data[1], # messageBody
            "b1": "yes", # option 1
            "b2": "", # option 2
            "b3": "no"  # option 3
    }]}
    }
    return messageData

def convertTupelToInfrafonMessageFormat(data) :
    '''
    Convert a tupel, which has the attributes for a infrafon message json,
    to the correct format to send that message over mqtt to an infrafon.
    The tupel consists of (subject, message).
    '''
    full_message =  {
	"app": {
		"pharmacy_quest": tupelToInfrafonMessageHelperFunc(data) 
	}
    }

    return full_message

def extractDataFromInfraonMqttPayload(data):
    '''
    Extract data from a infrafonMQTT message payload and check if it is the right payload.
    e.g.{"app": {"matrix": {"data": {"msglist": [{"id": "2", "reply": "yes"}]}}}}
    This function extracts the relevant data as a tupel (id, reply)
    '''
    data = data.split("{")
    if len(data) == 6:
        data = data[5]
        data = data.split("\"")
        return (data[3], data[7])
    # if the data has not the right format return error
    return("error", "wrong mqtt message")  


def checkTopicForMatrixDataview(topic):
    '''
    Check if a given topic comes from an infrafon with an Omnisecure-Dataview on it.
    A topic from a device with the Omnisecure-Dataview looks like this:
    "ife/Infrafon_dev/device/app-up/Omnisecure/240ac40a1454"
    '''
    topic = topic.split("/")
    if topic[4] == "pharmacy_quest":
        return True
    else:
        return False
    


async_client = AsyncClient(
    "https://matrix.freiburg.social", "infrafon-matrix"
)

async def publish(client, payload, top="buzzer"):
    '''
    Publishes messages, infrafon-buzzer commands and everything else connected to the mqtt.
    '''
    await client.publish(topic[str(top)], payload)

async def listen(client, infrafonMessageArrivedEvent):
    ''' 
    Subscribe to the infrafon-topic to recieve an answer
    from the infrafon, append the response in the last messages stack
    '''
    #async with aiomqtt.Client(hostname="infrafon.cloud", port=1883, username="lukas_dev", password="Welcome0!", client_id=f"infrafon-matrix-worker-{random(0, 1000)}") as client:
    async with client.messages() as messages:
        await client.subscribe(topic["subscribe"])
        async for message in messages:
            ####################################################################################
            # TODO  11111 add device id to msgs to sort them and make it possible to answer to the right device
            #######################################################################################
            print(message.payload)
            lastMessages.append(message.payload)
            infrafonMessageArrivedEvent.set()

            

async def waitForLastMessageStackToChange(infrafonMessageArrivedEvent, publishMessageInMatrixEvent, loop):
    '''
    Register new messages coming in the stack and processing them!
    '''
    # wait until the infrafonMessageArrivedEvent is triggered by a new message
    # from the listen() function
    await infrafonMessageArrivedEvent.wait()
    
    # Incoming messages are bitstrings, be careful
    # process the message
    if len(lastMessages) > 0:
        msg = lastMessages.pop()
        # check if the message is a reply or a delete notification to prevent stack overflow
        # b'{"app": {"matrix": {"data": {"msglist": [{"id": "1", "reply": "no"}]}}}}' --- reply
        # b'{"app": {"matrix": {"data": {"msglist": [{"id": "1", "del": true}]}}}}' --- delete
        ######################################################################################
        # ADD CUSTOM FILTER HERE
        ##################################################################################
        if b"reply" in msg:
            # check for the lock access request!!!
            if b"0" in msg:
                # create custom reply tuple to send the door request to the matrix chat
                if b"yes" in msg:
                    replyTuple = ("0", "yes")
                else:
                    replyTuple = ("0", "no")
                matrixMessagesToBePublished.append(replyTuple)
                #print("sending modifiyed tuple")
            else:
                replyTuple = extractDataFromInfraonMqttPayload(str(msg))
                matrixMessagesToBePublished.append(replyTuple)
                #print("sending tuple to stack")
        
    #print("resetting events")
    infrafonMessageArrivedEvent.clear()
    publishMessageInMatrixEvent.set()
    loop.create_task(waitForLastMessageStackToChange(infrafonMessageArrivedEvent, publishMessageInMatrixEvent, loop))


async def publishMatrixMessagesFromStack(async_client, room_id, publishMessageInMatrixEvent, loop):
    '''
    Publish messages in the matrixMessagesToBePublished Stack in the Matrix room
    '''
    await publishMessageInMatrixEvent.wait()
    if len(matrixMessagesToBePublished) > 0:
        msg = matrixMessagesToBePublished.pop()
        # check for the door access message
        if msg[0] == "0" and msg[1] == "yes":
            content = {
            "body": f"Infrafon-{deviceIdShort} request access to open the demo door.",
            "msgtype": "m.text"
            }
        elif msg[0] == "0" and msg[1] == "no":
            content = {
            "body": f"Infrafon-{deviceIdShort} does not want to request access to open the demo door.",
            "msgtype": "m.text"
            }
        else:
            print(contentArray)
            print(msg[0])
            content = {
            "body": f"The answer from infrafon-{deviceIdShort} to '{contentArray[int(msg[0])]}' is {msg[1]}",
            "msgtype": "m.text"
            }
        await async_client.room_send(room_id, 'm.room.message', content)
    publishMessageInMatrixEvent.clear()
    loop.create_task(publishMatrixMessagesFromStack(async_client, room_id, publishMessageInMatrixEvent, loop))

background_tasks = set()


def formatMatrixResponse(responseStr):
    '''
    Format a matrix response message to the subject and the message for the infrafon.
    This includes cutting out unecessary whitespaces, so they dont tamper with the 
    infrafon layout and spliting the message with ','. Furthermore we remove the keyword.
    '''
    response = responseStr.replace(matrixKeywords["publish"], "").strip()
    response = response.split(",")
    # remove leading spaces
    response[0] = response[0].lstrip()
    response[1] = response[1].lstrip()
    return response

async def sendMatrixMessage(message, async_client, room_id):
    content = {
        "body": f"{message}",
        "msgtype": "m.text"
        }
    await async_client.room_send(room_id, 'm.room.message', content)

# main function handling the matrix communication
async def main():
    # login to the matrix room
    response = await async_client.login("5Umv4JZX2vfHtK9")
    # print if the login was succesfull
    print(response)
    
    # we read the previously-written token...
    with open ("next_batch","r") as next_batch_token:
        # ... and well async_client to use it
        async_client.next_batch = next_batch_token.read()

    #async with aiomqtt.Client(hostname="infrafon.cloud", port=1883, username="lukas_dev", password="Welcome0!", client_id=f"infrafon-matrix-worker-{random(0, 1000)}") as client:
    async with aiomqtt.Client(hostname=mqttUrl, port=mqttPort, username=mqttUsername, password=mqttPassword, client_id=f"infrafon-matrix-worker-{random(0, 1000)}") as client:
        loop = asyncio.get_event_loop()

        ###################################################################################################################
        #                                                   EVENTS
        ###################################################################################################################
        # set up event for updating local device list
        updateLocalDeviceListEvent = asyncio.Event()
        # activate once for loading in the current list
        updateLocalDeviceListEvent.set()
        # set up event for incoming messages at the lastMessages stack
        infrafonMessageArrivedEvent = asyncio.Event()
        publishMessageInMatrixEvent = asyncio.Event()
        ###################################################################################################################
        #                                               TRAMPOLINE FUNCTIONS
        ###################################################################################################################
        loop.create_task(waitForLastMessageStackToChange(infrafonMessageArrivedEvent, publishMessageInMatrixEvent, loop))
        # hardcoded room id -- keep track!
        loop.create_task(publishMatrixMessagesFromStack(async_client, hard_coded_room_id, publishMessageInMatrixEvent, loop))
        # create the trampoline task for the updateLocalDeviceList funciton
        loop.create_task(updateLocalDeviceList(updateLocalDeviceListEvent, loop))
        ###################################################################################################################
        #                                                 BACKGROUND TASKS
        ###################################################################################################################
        # Listen for mqtt messages in an (unawaited) asyncio task
        task = loop.create_task(listen(client, infrafonMessageArrivedEvent))
        # Save a reference to the task so it doesn't get garbage collected
        background_tasks.add(task)
        task.add_done_callback(background_tasks.remove)
        
        ###################################################################################################################
        #                                                 MAIN LOOP
        ###################################################################################################################

        while (True):
            sync_response = await async_client.sync(30000) #3000
            with open("next_batch","w") as next_batch_token:
                next_batch_token.write(sync_response.next_batch)
                

            if len(sync_response.rooms.join) > 0:
                joins = sync_response.rooms.join
                for room_id in joins:
                    for event in joins[room_id].timeline.events:
                        print(event.body)
                        if hasattr(event, 'body') and event.body.startswith(matrixKeywords["buzzer"]):
                            # send mqtt message to the infrafon
                            await publish(client, buzzer_data_json)
                        elif hasattr(event, 'body') and event.body.startswith(matrixKeywords["publish"]):
                            # send mqtt message to the infrafon
                            # Dumps the seriallized json data into a python string "message
                            # get the attributes for the map from the matrix message
                            response = formatMatrixResponse(event.body)
                        
                            payloadMessage = json.dumps(convertTupelToInfrafonMessageFormat(response))
                            await publish(client, payloadMessage, "publish")    
                            await publish(client, buzzer_data_json, "buzzer")
                            await sendMatrixMessage("The message was delivered to the Infrafon!", async_client, room_id)
                            # start the task to process the reply
                            # loop.create_task(publishMatrixMessagesFromStack(async_client, room_id, publishMessageInMatrixEvent, loop))
                            # iterate the global message counter and add the content to the content array
                            global messageCounter
                            messageCounter = messageCounter + 1
                            contentArray.append(response[1])
                        elif hasattr(event, 'body') and event.body.startswith(matrixKeywords["grant"]):
                            # matrix message starting with 'grant access' -> activate passive nfc antenna
                            await publish(client, nfc_mqtt_data_grant_json, "access")
                            await sendMatrixMessage(f"Access has been granted to the infrafon-{deviceIdShort}", async_client, room_id)
                        elif hasattr(event, 'body') and event.body.startswith(matrixKeywords["revoke"]):
                            # matrix message starting with 'revoke access' -> deactivates passive nfc antenna
                            await publish(client, nfc_mqtt_data_revoke_json, "access")
                            await sendMatrixMessage(f"Access has been revoked from the infrafon-{deviceIdShort}", async_client, room_id)
                            
                            
            # we write the token to a file here
            with open("next_batch","w") as next_batch_token:
                next_batch_token.write(sync_response.next_batch)
            #print(sync_response) # note that this could be LARGE!
            # do some reading from sync_response

asyncio.run(main())