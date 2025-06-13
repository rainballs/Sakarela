from django.test import TestCase
from django.conf import settings
from store.views import _generate_signature, SIGN_ORDER
from store.utils import check_key_format, convert_key_to_pkcs8
import os
import logging

logger = logging.getLogger(__name__)

class MyPOSKeyFormatTestCase(TestCase):
    def setUp(self):
        self.key_path = settings.MYPOS_PRIVATE_KEY_PATH
        
    def test_key_format(self):
        """Test the private key format"""
        # First check the current format
        format_type, error = check_key_format(self.key_path)
        
        if error:
            self.fail(f"Error checking key format: {error}")
            
        # We're now using PKCS#1 format directly
        self.assertEqual(format_type, 'pkcs1', "Key should be in PKCS#1 format")
        logger.info("Key is in PKCS#1 format")

class MyPOSSignatureTestCase(TestCase):
    def setUp(self):
        self.params = {
            "IPCmethod": "IPCPurchase",
            "IPCVersion": "1.4",
            "IPCLanguage": "EN",
            "SID": settings.MYPOS_SID,
            "walletnumber": settings.MYPOS_WALLET,
            "Amount": "29.98",
            "Currency": "BGN",
            "OrderID": "test-order-id",
            "URL_OK": "http://127.0.0.1:8000/store/payment/result",
            "URL_Cancel": "http://127.0.0.1:8000/store/payment/result",
            "URL_Notify": "http://127.0.0.1:8000/store/payment/callback",
            "CardTokenRequest": "0",
            "KeyIndex": "1",
            "PaymentParametersRequired": "1",
            "customeremail": "test@example.com",
            "customerfirstnames": "Test",
            "customerfamilyname": "User",
            "customerphone": "0889402222",
            "customercountry": "BGR",
            "customercity": "Sofia",
            "customerzipcode": "1000",
            "customeraddress": "Test Street 1",
            "Note": "",
            "CartItems": "1"
        }
        
    def test_signature_generation(self):
        """Test signature generation with known parameters"""
        # First ensure the key is in the correct format
        key_test = MyPOSKeyFormatTestCase()
        key_test.setUp()
        key_test.test_key_format()
        
        # Generate signature
        try:
            signature = _generate_signature(self.params)
            self.assertIsNotNone(signature, "Signature should not be None")
            self.assertTrue(len(signature) > 0, "Signature should not be empty")
            
            # Log the signature and parameters for debugging
            logger.info("Generated signature: %s", signature)
            logger.info("Parameters used:")
            for param in SIGN_ORDER:
                logger.info("%s: %s", param, self.params.get(param, ''))
                
        except Exception as e:
            self.fail(f"Signature generation failed: {str(e)}")
            
    def test_signature_components(self):
        """Test each component that goes into the signature"""
        # Test parameter concatenation
        values = []
        for param in SIGN_ORDER:
            value = str(self.params.get(param, '')).strip()
            values.append(value)
            logger.info(f"Parameter {param}: {value}")
            
        concat_string = '-'.join(values)
        logger.info(f"Concatenated string: {concat_string}")
        
        # Verify each parameter is present
        for param in SIGN_ORDER:
            self.assertIn(param, self.params, f"Missing required parameter: {param}")
