import logging
import subprocess

import requests
import xml.etree.ElementTree as ET
from django.conf import settings

logger = logging.getLogger(__name__)


def check_key_format(key_path):
    """
    Check the format of a private key and return its type.
    Returns: ('pkcs1'|'pkcs8'|'unknown', error_message if any)
    """
    try:
        with open(key_path, 'r') as f:
            content = f.read()

        if "-----BEGIN RSA PRIVATE KEY-----" in content:
            return 'pkcs1', None
        elif "-----BEGIN PRIVATE KEY-----" in content:
            return 'pkcs8', None
        elif "-----BEGIN ENCRYPTED PRIVATE KEY-----" in content:
            return 'encrypted', "Encrypted keys are not supported"
        else:
            return 'unknown', "Unknown key format"

    except Exception as e:
        return 'unknown', str(e)


def convert_key_to_pkcs8(input_path, output_path):
    """
    Convert a PKCS#1 key to PKCS#8 format
    """
    try:
        # First verify it's a valid PKCS#1 key
        result = subprocess.run([
            'openssl', 'rsa',
            '-in', input_path,
            '-check'
        ], capture_output=True, text=True)

        if result.returncode != 0:
            return False, f"Invalid RSA key: {result.stderr}"

        # Convert to PKCS#8
        result = subprocess.run([
            'openssl', 'pkcs8',
            '-topk8',
            '-in', input_path,
            '-out', output_path,
            '-nocrypt'
        ], capture_output=True, text=True)

        if result.returncode == 0:
            return True, "Successfully converted key to PKCS#8"
        else:
            return False, f"Conversion failed: {result.stderr}"

    except Exception as e:
        return False, f"Error during conversion: {str(e)}"


def generate_econt_label_xml(order=None):
    import xml.etree.ElementTree as ET

    root = ET.Element("parcels")

    client = ET.SubElement(root, "client")
    ET.SubElement(client, "username").text = "iasp-dev"
    ET.SubElement(client, "password").text = "1Asp-dev"

    loadings = ET.SubElement(root, "loadings")
    row = ET.SubElement(loadings, "row")

    sender = ET.SubElement(row, "sender")
    ET.SubElement(sender, "name").text = "Тест клиент"
    ET.SubElement(sender, "phone_num").text = "+359888888888"
    ET.SubElement(sender, "city").text = "София"
    ET.SubElement(sender, "post_code").text = "1000"

    receiver = ET.SubElement(row, "receiver")
    ET.SubElement(receiver, "name").text = "Иван Тестов"
    ET.SubElement(receiver, "phone_num").text = "+359888123456"
    ET.SubElement(receiver, "email").text = "test@econt.com"
    ET.SubElement(receiver, "city").text = "София"
    ET.SubElement(receiver, "post_code").text = "1404"
    ET.SubElement(receiver, "street").text = "бул. България 1"

    shipment = ET.SubElement(row, "shipment")
    ET.SubElement(shipment, "shipment_type").text = "PACK"
    ET.SubElement(shipment, "weight").text = "1"

    services = ET.SubElement(row, "services")
    ET.SubElement(services, "cd").text = "1"
    ET.SubElement(services, "cd_currency").text = "BGN"
    ET.SubElement(services, "cd_amount").text = "1.00"

    return ET.tostring(root, encoding="utf-8", xml_declaration=True)



def send_econt_label_request(order):
    xml_data = generate_econt_label_xml(order)

    print("=== Outgoing XML to Econt ===")
    print(xml_data.decode("utf-8"))

    url = getattr(settings, "ECONT_LABEL_URL", "https://demo.econt.com/ee/services/LabelService")
    auth = (
        getattr(settings, "ECONT_USERNAME", "iasp-dev"),
        getattr(settings, "ECONT_PASSWORD", "1Asp-dev")
    )
    
    headers = {
        "Content-Type": "application/xml",
        "Accept": "application/xml",
    }
    logger.info(f"Sending Econt label request for order {order.id}")
    response = requests.post(url, data=xml_data, auth=auth, headers=headers)
    logger.info(f"Econt response status: {response.status_code}")
    logger.debug(f"Econt response content: {response.content}")
    return response


def handle_econt_response(response):
    print("=== Econt raw response ===")
    print(response.status_code)
    print(response.content.decode(errors="replace"))

    if response.status_code == 200 and response.content.strip():
        tree = ET.fromstring(response.content)
        shipment_num = tree.findtext(".//shipment_num")
        pdf_url = tree.findtext(".//pdf_url")
        return shipment_num, pdf_url
    else:
        raise Exception(f"Празен или грешен отговор от Econt:\n{response.status_code}\n{response.text}")
