from cryptography.fernet import Fernet

key = Fernet.generate_key()
print("Your encrypting key:")
print(key.decode())