## Manus API (Python)

# Manus API Key

sk-VLNSc5UtB-zMSFyEh7T6zGmIhQRUinPOgM5fD9_M7lmXqMxGHKbGvaHcHqEsR43PKf6SJdNLmhmy4oYWZQIgngi46Q-2

# Create Task

import requests

url = "https://api.manus.ai/v1/tasks"

payload = {
    "prompt": "<string>",
    "attachments": [
        {
            "filename": "<string>",
            "url": "<string>",
            "mimeType": "<string>",
            "fileData": "<string>"
        }
    ],
    "taskMode": "chat",
    "connectors": ["<string>"],
    "hideInTaskList": True,
    "createShareableLink": True,
    "taskId": "<string>",
    "agentProfile": "speed",
    "locale": "<string>"
}
headers = {
    "API_KEY": "<api-key>",
    "Content-Type": "application/json"
}

response = requests.post(url, json=payload, headers=headers)

print(response.json())


# Get Task

import requests

url = "https://api.manus.ai/v1/tasks"

headers = {"API_KEY": "<api-key>"}

response = requests.get(url, headers=headers)

print(response.json())

# Update Task

import requests

url = "https://api.manus.ai/v1/tasks/{task_id}"

payload = {
    "title": "<string>",
    "enableShared": True,
    "enableVisibleInTaskList": True
}
headers = {
    "API_KEY": "<api-key>",
    "Content-Type": "application/json"
}

response = requests.put(url, json=payload, headers=headers)

print(response.json())

# Delete Task

import requests

url = "https://api.manus.ai/v1/tasks/{task_id}"

headers = {"API_KEY": "<api-key>"}

response = requests.delete(url, headers=headers)

print(response.json())

