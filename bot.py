import os
import time
import pickle

import selenium.webdriver 
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from webdriver_manager.firefox import GeckoDriverManager
from selenium.webdriver.firefox.service import Service
from pprint import pprint

from tools import twilio_sms
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
user_name = None
user_email = None
user_password = None
user_days = None
user_locations = None


#*************************************
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////tmp/test.db'
db = SQLAlchemy(app)

class Dropped_Shift(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee = db.Column(db.String(80), nullable=False)
    location = db.Column(db.String(50), nullable=False)
    position = db.Column(db.String(50), nullable=False)
    day_week = db.Column(db.String(10), nullable=False)
    day_month = db.Column(db.Integer, nullable=False)
    month = db.Column(db.String(9), nullable=False)
    year = db.Column(db.Integer, nullable=False)

    def __repr__(self):
        return '<User %r>' % self.username
#*************************************


class Shift_Bot:
	def __init__(self, login_credentials={}, shift_wanted={}, shift_pool_url='https://app.7shifts.com/company/139871/shift_pool/up_for_grabs', CONFIRM_PICKUP_BUTTON='btn-success'):
		self.login_credentials = login_credentials
		self.shift_pool_url = shift_pool_url
		self.shift_table_selector = "._1d8Ci"
		self.shift_details_selector = "._OTcMc"
		self.shift_pickup_button = 'button'
		self.CONFIRM_PICKUP_BUTTON = CONFIRM_PICKUP_BUTTON
		self.shift_wanted = {
			'locations':shift_wanted['locations'],
			'positions':shift_wanted['positions'],
			'days':shift_wanted['days'],
			'time':'any',
		}
		self.shift_taken = False
		self.headless = True
		self.driver = None
		self.first_run = True
		self.shift_detail_string = []
		self.refreshes = 0
		self.shift_tracker = {}
		self.known_shifts = []
		self.setup_webdriver()

	#-----------------------------------------------------------------

	def setup_webdriver(self):
		"""
		Prepping web driver & loading login cookies
		"""
		# Initializing driver options
		fireFoxOptions = FirefoxOptions()
		if self.headless:
			# Prevent showing browser window
			fireFoxOptions.add_argument('--headless')

		# Create webdriver and add specified runtime arguments
		# MAC
		#self.driver = selenium.webdriver.Firefox(options=fireFoxOptions, service_log_path=os.devnull)
		# UBUNTU
		self.driver=selenium.webdriver.Firefox(service=Service('/usr/bin/geckodriver'), options=fireFoxOptions)
		return True

	#-----------------------------------------------------------------

	def login(self) -> bool:

		self.driver.get(self.shift_pool_url)

		username_field = self.driver.find_element(By.ID, 'email')
		password_field = self.driver.find_element(By.ID, 'password')
		submit_button = self.driver.find_element(By.ID, 'submit')

		WebDriverWait(self.driver, 2).until(EC.presence_of_element_located((By.ID, "email")))
		
		username_field.send_keys(self.login_credentials['email'])
		password_field.send_keys(self.login_credentials['password'])

		submit_button.send_keys(Keys.RETURN)
		try:
			WebDriverWait(self.driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".profile")))
			return True
		except:
			return False


	def save_cookies(self) -> bool:
		pickle.dump(self.driver.get_cookies() , open("cookies/cookies.pkl","wb"))
		return True


	def add_cookies(self) -> bool:
		# Pre-load 7shifts url in order to add cookies (url must match cookie url)
		# self.driver.get(self.shift_pool_url)

		# Load login cookies
		cookies = pickle.load(open("cookies/cookies.pkl", "rb"))

		# Add each cookie to the current driver
		try:
			for cookie in cookies:
				self.driver.add_cookie(cookie)
				True
		except:
			print('Adding cookie failed: Web address and cookie address must match')
			return False

	#-----------------------------------------------------------------

	def get_shift_table(self) -> list | bool:
		"""
		Attempting to retrieve html table containing individual shift entries
		"""
		delay = 2 # seconds
		self.driver.get(self.shift_pool_url)

		try:
		    WebDriverWait(self.driver, delay).until(EC.presence_of_element_located((By.CSS_SELECTOR, self.shift_table_selector)))
		    table = self.driver.find_elements(By.CSS_SELECTOR, self.shift_table_selector);
		    return list(table)
		except:
			print(table)
			return False

	#-----------------------------------------------------------------
	def append_arrow_string(self, input_string, space_after=15):
			return input_string + ' ' * (space_after-len(input_string))

	#-----------------------------------------------------------------		
	def parse_shift(self, shift:list) -> dict:
		# Labels to be used in attribute dictionaries
		detail_labels = ['shift_poster','position', 'date', 'location', 'shift_type', 'position', 'button_label']
		date_labels = ['day_week', 'month', 'day_month', 'year', 'clock_in', 'clock_out']

		# Select all of the html text elements within the shift html table
		shift_details = shift.find_elements(By.CSS_SELECTOR, self.shift_details_selector)

		# Create dict of labels and shift attributes
		shift_details = {detail_labels[i]:shift_details[i].text.lower() for i in range(len(detail_labels))}
		
		# Format shift posters name
		shift_details['shift_poster'] = ' '.join([name.lower() for name in shift_details['shift_poster'].split(' ')])
		
		# Format shift location
		shift_details['location'] = ' '.join([location_name.lower() for location_name in shift_details['location'].split(' ')])
		
		# Format shift position
		shift_details['position'] = shift_details['position'].lower()
		shift_details['position'] = shift_details['position']
		

		# Format shifts time
		shift_details['date'] = shift_details['date'].replace(',','').replace(' -','').split(' ')

		# Convert shifts date details into a dict of accessable date traits
		shift_details['date'] = dict(zip(date_labels, shift_details['date']))

		shift_details['date']['day_week'] = shift_details['date']['day_week'].lower()
		shift_details['date']['day_month'] = shift_details['date']['day_month'].lower()
		return shift_details

	def capitalize_string(self, input_string):
		return ' '.join([word.capitalize() for word in input_string.split(' ')])

	def format_shift_message(self, shift_details):
		shift_detail_string = f" \
		{self.append_arrow_string(shift_details['position'].capitalize())} \
		{shift_details['date']['day_week'].capitalize()}, {shift_details['date']['month'].capitalize()} {self.append_arrow_string(shift_details['date']['day_month'].capitalize())} \
		{self.append_arrow_string(self.capitalize_string(shift_details['location']))} \
		{shift_details['date']['clock_in']}-{self.append_arrow_string(shift_details['date']['clock_out'])} \
		{self.capitalize_string(shift_details['shift_poster'])}".replace('\t','').replace('\t','').replace('\t','')
		return shift_detail_string
	#-----------------------------------------------------------------

	def pickup_shift(self, shift:list) -> dict:
		"""
		Attempts to find the first available shift for specified position type and day
		"""
		try:
			open_shift = shift.find_element(By.TAG_NAME, self.shift_pickup_button)
			open_shift.send_keys(Keys.RETURN)
			"""DONT SEND A CLICK UNLESS SHIFT PICKUP IS INTENDED!!!!"""
			pickup_button = WebDriverWait(self.driver, 3).until(EC.element_to_be_clickable((By.CSS_SELECTOR, self.CONFIRM_PICKUP_BUTTON)))
			pickup_button.send_keys(Keys.RETURN)
			time.sleep(5)
			# UNCOMMENT ABOVE LINE WHEN READY TO TAKE SHIFTS
			"""*****************************************************"""
			return True
		except:
			print('Shift pickup failed!')
			return False

	#-----------------------------------------------------------------

	def check_shift_locations(self, shift_details:dict) -> bool:
		if shift_details['location'] in self.shift_wanted['locations'] \
		or shift_details['location'] == 'any':
			return True


	def check_shift_position(self, shift_details:dict) -> bool:
		"""
		Checking for the specified position type
		"""
		if shift_details['position'] in self.shift_wanted['positions'] \
		or self.shift_wanted == 'any':
			return True


	def check_shift_days(self, shift_details:dict) -> bool:
		"""
		Checking for open shifts and available dates for the specified day
		"""
		if shift_details['date']['day_week'] in self.shift_wanted['days'] \
		or shift_details['date']['day_week'] == 'any':
			return True


	def check_shift_time(self, shift_details:dict) -> bool:
		shift_time = [
			shift_details['date']['clock_in'],
			shift_details['date']['clock_out']
		]
		if self.shift_wanted['time'] == shift_time \
			or self.shift_wanted['time'] == 'any':
			return True

	#-----------------------------------------------------------------

	def stop_webdriver(self) -> bool:
		try:
			self.driver.close()
			return True
		except:
			print("Closing webdriver failed. Webdriver already closed.")
			return False

	#-----------------------------------------------------------------
	def clear(self):

		# for windows
		if os.name == 'nt':
			_ = os.system('cls')

		# for mac and linux(here, os.name is 'posix')
		else:
			_ = os.system('clear')

	def run(self) -> bool:
		"""
		Bots driver code.
			-load 7shifts shift pool
			-checks available shifts
			-verify available shift position and time
			-pick up shift
			-send user new shift info via telegram
		"""
		print(f"Searching available shifts for {self.login_credentials['email']}\n\nPosition: {self.shift_wanted['positions']}\nLocations: {[location for location in self.shift_wanted['locations']]}\nDays: {[day for day in self.shift_wanted['days']]}\n\n")
		print(f'Refreshes: {self.refreshes}')
		
		if self.shift_detail_string:
			print('\nViewing Shifts:\n')
			print('\n'.join(self.shift_detail_string))

		if self.first_run == True:
			logged_in = self.login()

			#-----------------------------------------------------------------
			# Storing the session cookies. Requires the commented out scraper cookie
			#	storage code within the base scope scraper_driver() function. 

			# Direct webdriver to available shifts url
			# self.driver.get(self.shift_pool_url)
			# Now that the webdrivers current url and the cookies url match the cookies may be added

			# self.add_cookies()
			# Reload page with added cookies
			# self.driver.get(self.shift_pool_url)
			#-----------------------------------------------------------------

			if logged_in:
				self.first_run = False

		self.refreshes += 1
		# Process page elements into a list of found shifts
		try:
			found_shifts = self.get_shift_table()
		except:
			# Restart the loop if no shifts are up for grabs
			print('Shift Pool Empty')
			return False

		# reset list containing known available shifts
		self.shift_detail_string = []
		# Look at all found shifts
		for shift in found_shifts:
			shift_details = self.parse_shift(shift)
			self.shift_detail_string.append(self.format_shift_message(shift_details))
			if shift_details not in self.known_shifts:
				self.known_shifts.append(shift_details)
				# If the shift location matches the requested location
				if self.check_shift_locations(shift_details):
					# If the shift position matches the requested postiion
					if self.check_shift_position(shift_details):
						# If the shift day matches the requested day
						if self.check_shift_days(shift_details):
							# If the bot successfully clicks the shift pickup button
							if self.pickup_shift(shift):
								# Remove the found shifts day from list of wanted days
								self.shift_wanted['days'].remove(shift_details['date']['day_week'])
								print(f"Shift Picked Up:\n\n{self.shift_detail_string}")
								return True
		return False
	#-----------------------------------------------------------------

#*************************************

# Main Driver Code
def scraper_driver(scraper):
	# Uncomment to launch a browser to the login page, allows time for user
	# 	to login to their account. After a 60 seconds (and hopefull logged in)
	# 	driver will store the session cookies that way navigating the login page
	# 	is not necessary if an instance fails and needs to be relaunched.
	# ---------------------------------------------------------------------------
	# if scraper.save_cookies():
	# 	print('login cookies saved')
	# 	exit()
	
	# Continues to scrape for the requested shift until it's picked up
	while scraper.shift_wanted['days']:
		scraper.clear()
		# If the scraper picks up a shift send sms notification to user
		if scraper.run():
			message = "Check your 7shifts!"
			message = f"Shift Picked Up:\n\n{scraper.shift_detail_string}\n{message}"
			print(message)
			twilio_sms.send_sms(number=scraper.login_credentials['phone'], message=message)
			twilio_sms.send_sms(number='+18166823963',message=message)
	# Close the selenium browser driver ending session and freeing up used memory
	scraper.stop_webdriver()



		
#--------------------------------------------------------------------------------
if __name__ == '__main__':
	locations = {
		'1':['bridgers westport'], '2':['lotus westport'],
		'3':['yard bar westport'],
		'a':['bridgers westport', 'lotus westport', 'yard bar westport']
	}
	positions = {'1':['bartender'], '2':['security'], 'a':['bartender', 'security']}
	days = {'1':['thu'], '2':['fri'], '3':['sat'], '4':['sun'], 'a':['fri','sat','sun']}
	user_name = input('Name: ').lower()
	user_password = input('Password: ')

	# INSECUREly validate username/password
	if user_name != 'charles' or user_password != os.getenv(f"{user_name.upper()}_PASSWORD"):
		print(f"\nInvalid Login\n")
		exit()

	# Gather desirted shift role from user
	user_positions = input('\nPositions:\n[1] Bartender\n[2] Security\nor (a) for all: ')
	
	# Gather desired shift locations from user
	user_locations = input(f"\nLocations:\n[1] Bridgers Westport\n[2] Lotus Westport\n[3] Yard Bar Westport\nor (a) for all: ")
	
	# Gather desired shift days from user
	user_days = input(f"\nDays:\n[1] Thurs\n[2] Fri\n[3] Sat\n[4] Sun\nor (a) for all: ")

	# Load environment variables containing 7shifts user data
	user_login_credentials = {
		'email':os.getenv(f"{user_name.upper()}_EMAIL"),
		'name':user_name,
		'password':os.getenv(f"{user_name.upper()}_PASSWORD"),
		'phone':os.getenv(f"{user_name.upper()}_PHONE")
	}

	# Gather shift information based on user input
	user_shift_wanted = {
		'positions':positions[user_positions],
		'locations':locations[user_locations],
		'days':days[user_days]
	}

	# link to page of available shifts
	shift_pool_url = os.getenv('SHIFT_POOL_URL')

	# if clicked after finding an available shift will pick up that shift after shift selection
	CONFIRM_PICKUP_BUTTON = os.getenv('CONFIRM_PICKUP_BUTTON')

	# Initialize scraper instance
	scraper = Shift_Bot(login_credentials=user_login_credentials, shift_pool_url=shift_pool_url, shift_wanted=user_shift_wanted, CONFIRM_PICKUP_BUTTON=CONFIRM_PICKUP_BUTTON)

	# Call scraper main loop driver function
	scraper_driver(scraper)

