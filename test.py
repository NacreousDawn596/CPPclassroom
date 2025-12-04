import requests
import urllib3
import base64
import json

# Disable SSL warnings for self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def post_login_data(url: str, email: str, password: str):
    """
    Sends a POST request to a specified URL with email and password data.

    Args:
        url (str): The URL to send the POST request to.
        email (str): The user's email address.
        password (str): The user's password.

    Returns:
        requests.Response: The response object from the POST request.
    """
    payload = {
        'email': email,
        'password': password
    }
    
    # Headers to match the API's expected format
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json, text/plain, */*',
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:138.0) Gecko/20100101 Firefox/138.0',
        'Referer': 'https://egrading.ensam-umi.ac.ma/auth/login',
        'Origin': 'https://egrading.ensam-umi.ac.ma'
    }
    
    # Use json=payload to send JSON, verify=False to bypass SSL certificate verification
    response = requests.post(url, json=payload, headers=headers, verify=False)
    return response

def jbd_hadik_data_mn_token(token: str) -> dict:
    """
    Decodes a JWT token to extract student data from its payload,
    excluding standard JWT claims.

    Args:
        token (str): The JWT token string.

    Returns:
        dict: A dictionary containing the extracted student data.
    """
    payload_b64 = token.split('.')[1]

    # Python's urlsafe_b64decode handles URL-safe characters ('-' and '_')
    # and also manages padding for JWT-like strings.
    decoded_payload_bytes = base64.urlsafe_b64decode(payload_b64.encode('utf-8'))
    decoded = json.loads(decoded_payload_bytes.decode('utf-8'))

    excluded_keys = ['role', 'exp', 'iat', 'sub']
    student_data = {k: v for k, v in decoded.items() if k not in excluded_keys}

    return student_data


print(jbd_hadik_data_mn_token(post_login_data("https://egrading.ensam-umi.ac.ma/api/auth/login", "m24331@ensam.ac.ma", "M24331a457").json()['accessToken']))