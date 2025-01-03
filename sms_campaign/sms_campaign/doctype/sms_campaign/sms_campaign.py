# Copyright (c) 2023, Finesoft Afrika and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils.safe_exec import get_safe_globals
from frappe.core.doctype.sms_settings.sms_settings import send_sms
from frappe.utils import cast

class SMSCampaign(Document):
	
	def before_insert(self):
		query_params  = frappe.get_doc("SMS Campaign Query", self.query).params
		self.params = []
		for param in query_params:
			self.append("params", {
				"label": param.label,
				"value": param.value
			})
	
	def send_non_triggered_sms(self):
		parameters = {}
		for param in self.params:
			parameters[param.label] = param.value
		self.send_sms(parameters)

	def onload(self):
		if self.trigger_type == "DIRECT" or self.trigger_type == "SCHEDULED":
			parameters = {}
			for param in self.params:
				parameters[param.label] = param.value

			query = frappe.get_doc("SMS Campaign Query", self.query)
			data = frappe.db.sql(query.query, parameters, as_dict=True)

			if len(data) < 1:
				frappe.msgprint("This query does not return any data. Therefore, no parameters and sms list will be shown.", title="No data for selected query")
				return
			
			columns = list(data[0].keys())
			self.set_onload("columns", columns)
			rows = []
			for row in data:
				row["message"] = frappe.render_template(self.message, get_context(row))
				rows.append(row)
			
			self.set_onload("rows", rows)

		else:
			parameters = {}
			doc = frappe.get_all(self.trigger_doctype, ("name"), limit=1, order_by="creation desc")[0]
			parameters[frappe.db.get_value("SMS Campaign Query", self.query, "doc_name_field")] = doc.name
			for param in self.params:
				parameters[param.label] = param.value

			query = frappe.get_doc("SMS Campaign Query", self.query)
			data = frappe.db.sql(query.query, parameters, as_dict=True)

			if len(data) < 1:
				frappe.msgprint("This query does not return any data. Therefore, no parameters and sms list will be shown.", title="No data for selected query")
				return
			
			columns = list(data[0].keys())
			self.set_onload("columns", columns)
			rows = []
			for row in data:
				row["message"] = frappe.render_template(self.message, get_context(row))
				rows.append(row)
			
			self.set_onload("rows", rows)

	def update_next_run_date(self):
		self.last_run_date = frappe.utils.nowdate()

		match self.repeats:
			case "Daily":
				self.next_run_date = frappe.utils.add_days(self.last_run_date, self.repeats_every)
			case "Weekly":
				self.next_run_date = frappe.utils.add_days(self.last_run_date, self.repeats_every * 7)	
			case "Monthly":
				self.next_run_date = frappe.utils.add_months(self.last_run_date, self.repeats_every)
			case "Yearly":
				self.next_run_date = frappe.utils.add_months(self.last_run_date, self.repeats_every * 12)

	
	def send_triggered_sms(self, doc_name):
		parameters = {}
		parameters[frappe.db.get_value("SMS Campaign Query", self.query, "doc_name_field")] = doc_name
		for param in self.params:
			parameters[param.label] = param.value
		self.send_sms(parameters)

	def on_submit(self):
		if self.trigger_type == "DIRECT":
			self.send_non_triggered_sms()
		
		if self.trigger_type == "SCHEDULED":
			self.next_run_date = self.start_date
			
		self.save()

	def send_sms(self, parameters):
		query = frappe.get_doc("SMS Campaign Query", self.query)

		if self.channel == 'SMS':
			frappe.enqueue(
				"sms_campaign.sms_campaign.queue.send_sms_queued",
				queue="default",
				timeout=4000,
				query=query,
				parameters=parameters,
				template=self.message
			)
			frappe.msgprint("The send sms job has been queued")
		else:
			frappe.enqueue(
				"sms_campaign.sms_campaign.queue.send_email_queued",
				queue="default",
				timeout=4000,
				query=query,
				parameters=parameters,
				template=self.message,
				subject=self.email_subject,
				attachements=self.attachments,
			)
			frappe.msgprint("The send sms job has been queued")

		# data = frappe.db.sql(query.query, parameters, as_dict=True)
		# for row in data:
		# 	phone = row[query.phone_field]
		# 	msg=frappe.render_template(self.message, get_context(row))
		# 	phone = format_phone_number(phone)

		# 	if phone:
		# 		receiver_list = [phone]
		# 		send_sms(receiver_list = receiver_list, msg = msg)
		# 		frappe.db.commit()
			# send_sms(receiver_list = phone, msg = msg)
						

def format_phone_number(mobile_number):
    if mobile_number is None:
        return None
       
    if len(mobile_number) == 10:
        return "254" + mobile_number[1:]
    elif len(mobile_number) == 9:
        return "254" + mobile_number
    elif len(mobile_number) == 12:
        return "254" + mobile_number[3:]
    elif len(mobile_number) == 13:
        return "254" + mobile_number[4:]
    elif len(mobile_number) == 11:
        return "254" + mobile_number[2:]
    elif len(mobile_number) == 14:
        return "254" + mobile_number[5:]

    return None

def get_context(data):
	data["nowdate"] = frappe.utils.nowdate
	data["frappe"] = frappe._dict(utils=get_safe_globals().get("frappe").get("utils"))

	return data
	
def send_sheduled_sms():
	sms_campaigns = frappe.get_all("SMS Campaign", filters={"trigger_type": "SCHEDULED", "docstatus": 1, "active":1, "next_run_date": frappe.utils.nowdate()})
	for sms_campaign in sms_campaigns:
		sms_campaign = frappe.get_doc("SMS Campaign", sms_campaign.name)

		sms_campaign.send_non_triggered_sms()
		sms_campaign.update_next_run_date()

def send_triggered_after_insert_sms(doc, method=None):
	sms_campaigns = frappe.get_all("SMS Campaign", filters={"trigger_type": "TRIGGERED", "docstatus": 1, "active":1, "trigger": "New", "trigger_doctype": doc.doctype})
	for sms_campaign in sms_campaigns:
		sms_campaign = frappe.get_doc("SMS Campaign", sms_campaign.name)

		
		sms_campaign.send_triggered_sms(doc.name)

def send_triggered_on_submit_sms(doc, method=None):
	sms_campaigns = frappe.get_all("SMS Campaign", filters={"trigger_type": "TRIGGERED", "docstatus": 1, "active":1, "trigger": "Submit", "trigger_doctype": doc.doctype})
	for sms_campaign in sms_campaigns:
		sms_campaign = frappe.get_doc("SMS Campaign", sms_campaign.name)
		
		sms_campaign.send_triggered_sms(doc.name)

def send_triggered_on_cancel_sms(doc, method=None):
	sms_campaigns = frappe.get_all("SMS Campaign", filters={"trigger_type": "TRIGGERED", "docstatus": 1, "active":1, "trigger": "Cancel", "trigger_doctype": doc.doctype})
	for sms_campaign in sms_campaigns:
		sms_campaign = frappe.get_doc("SMS Campaign", sms_campaign.name)

		
		sms_campaign.send_triggered_sms(doc.name)


def send_triggered_on_update_sms(doc, method=None):
	#print("Triggered on update")
	sms_campaigns = frappe.get_all("SMS Campaign", filters={"trigger_type": "TRIGGERED", "docstatus": 1, "active":1, "trigger": "Update", "trigger_doctype": doc.doctype})
	for sms_campaign in sms_campaigns:
		sms_campaign = frappe.get_doc("SMS Campaign", sms_campaign.name)
		
		sms_campaign.send_triggered_sms(doc.name)
		

	#print(doc.doctype)
	sms_campaigns = frappe.get_all("SMS Campaign", filters={"trigger_type": "TRIGGERED", "docstatus": 1, "active":1, "trigger": "Value Change", "trigger_doctype": doc.doctype})
	#print(sms_campaigns)
	for sms_campaign in sms_campaigns:
		#print("trying to send sms right here: ")
		campaign = frappe.get_doc("SMS Campaign", sms_campaign.name)
		
		if frappe.db.has_column(doc.doctype, campaign.value_changed):
			doc_before_save = doc.get_doc_before_save()
			field_value_before_save = doc_before_save.get(campaign.value_changed) if doc_before_save else None

			fieldtype = doc.meta.get_field(campaign.value_changed).fieldtype
			if cast(fieldtype, doc.get(campaign.value_changed)) == cast(fieldtype, field_value_before_save):
				# value not changed
				return
			#print("trying to send sms right here: ")
			#print(doc.get(campaign.value_changed))
			if doc.get(campaign.value_changed) == campaign.new_value or not campaign.new_value or campaign.new_value == "":
				campaign.send_triggered_sms(doc.name)


def eval_condition(campaign):
	context = get_context(campaign)

	if campaign.condition:
		if not frappe.safe_eval(campaign.condition, None, context):
			return False
	
	return True

			
