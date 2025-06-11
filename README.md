# Sakarela-Backup

## myPOS integration

This project includes a simple integration with [myPOS](https://www.mypos.com/) for processing card payments. Below are the basic steps to configure the project with the myPOS test environment.

1. **Create a myPOS account** – register at the myPOS website and request access to the developer/test portal.
2. **Obtain test credentials** – within the myPOS portal create a virtual POS terminal and download the private key provided for test transactions.
3. **Place the key** – create a folder named `mypos` in the project root and copy the downloaded `private_key.pem` inside it. The `Sakarela_DJANGO/settings.py` file expects the key at `BASE_DIR / 'mypos/private_key.pem'`.
4. **Configure settings** – set the following variables in `settings.py` (or via environment variables in production):

   ```python
   MYPOS_CLIENT_NUMBER = '<your client number>'
   MYPOS_TERMINAL_ID = '<your terminal id>'
   ```

5. **Use the test checkout URL** – the payment form now reads the URL from `settings.MYPOS_BASE_URL`. By default it posts to `https://www.mypos.com/vmp/checkout-test`, which is the myPOS sandbox.
6. **Run the application** – start the Django development server with `python manage.py runserver` and place an order choosing "card" as the payment method. You will be redirected to the myPOS test gateway.

The payment view automatically signs the redirect parameters using the RSA key above. No manual signature files are required – simply ensure `private_key.pem` is present.

When you are ready to switch to production simply set `MYPOS_BASE_URL` to `https://www.mypos.com/vmp/checkout` and provide your live credentials.

