from flask import Flask, jsonify, request
from app import app, db
from app.models.Transactions.UTR.UTREntryModels import UTRHead, UTRDetail
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import func
from app.utils.CommonGLedgerFunctions import fetch_company_parameters, get_accoid
import os
import requests

# Get the base URL from environment variables
API_URL = os.getenv('API_URL')

# Import schemas from the schemas module
from app.models.Transactions.UTR.UTREntrySchema import UTRHeadSchema, UTRDetailSchema

# Global SQL Query
UTR_DETAILS_QUERY = '''
    SELECT Bank.Ac_Name_E AS bankAcName, Mill.Ac_Name_E AS millName
    FROM dbo.nt_1_utr
    LEFT OUTER JOIN dbo.nt_1_accountmaster AS Mill ON dbo.nt_1_utr.mill_code = Mill.Ac_Code AND dbo.nt_1_utr.mc = Mill.accoid AND dbo.nt_1_utr.Company_Code = Mill.company_code
    LEFT OUTER JOIN dbo.nt_1_accountmaster AS Bank ON dbo.nt_1_utr.bank_ac = Bank.Ac_Code AND dbo.nt_1_utr.ba = Bank.accoid AND dbo.nt_1_utr.Company_Code = Bank.company_code
    LEFT OUTER JOIN dbo.nt_1_utrdetail ON dbo.nt_1_utr.utrid = dbo.nt_1_utrdetail.utrid
    WHERE dbo.nt_1_utr.utrid = :utrid
'''

# Define schemas
utr_head_schema = UTRHeadSchema()
utr_head_schemas = UTRHeadSchema(many=True)

utr_detail_schema = UTRDetailSchema()
utr_detail_schemas = UTRDetailSchema(many=True)

def format_dates(task):
    return {
        "doc_date": task.doc_date.strftime('%Y-%m-%d') if task.doc_date else None,
    }

# Get data from both tables UTRHead and UTRDetail
@app.route(API_URL + "/getdata-utr", methods=["GET"])
def getdata_utr():
    try:
        Company_Code = request.args.get('Company_Code')
        Year_Code = request.args.get('Year_Code')
        if not all([Company_Code, Year_Code]):
            return jsonify({"error": "Missing required parameters"}), 400

        records = UTRHead.query.filter_by(Company_Code=Company_Code, Year_Code=Year_Code).all()

        if not records:
            return jsonify({"error": "No records found"}), 404

        all_records_data = []

        for record in records:
            utr_head_data = {column.name: getattr(record, column.name) for column in record.__table__.columns}
            utr_head_data.update(format_dates(record))

            utrid = record.utrid
            additional_data = db.session.execute(text(UTR_DETAILS_QUERY), {"utrid": utrid})
            additional_data_row = additional_data.fetchone()

            label = dict(additional_data_row._mapping) if additional_data_row else {}

            detail_records = UTRDetail.query.filter_by(utrid=utrid).all()
            detail_data = [{column.name: getattr(detail_record, column.name) for column in detail_record.__table__.columns} for detail_record in detail_records]

            record_response = {
                "utr_head_data": utr_head_data,
                "labels": label,
                "utr_details": detail_data
            }

            all_records_data.append(record_response)

        response = {
            "all_data_utr": all_records_data
        }
        return jsonify(response), 200

    except Exception as e:
        return jsonify({"error": "Internal server error", "message": str(e)}), 500

# Get data by the particular doc_no
@app.route(API_URL + "/getutrByid", methods=["GET"])
def getutrByid():
    try:
        doc_no = request.args.get('doc_no')
        company_code = request.args.get('Company_Code')
        Year_Code = request.args.get('Year_Code')
        if not all([doc_no, company_code, Year_Code]):
            return jsonify({"error": "Document number, Company Code, or Year Code not provided"}), 400

        utr_head = UTRHead.query.filter_by(doc_no=doc_no, Company_Code=company_code, Year_Code=Year_Code).first()
        if not utr_head:
            return jsonify({"error": "No records found"}), 404

        utr_id = utr_head.utrid
        additional_data = db.session.execute(text(UTR_DETAILS_QUERY), {"utrid": utr_id})
        additional_data_row = additional_data.fetchone()

        label = dict(additional_data_row._mapping) if additional_data_row else {}

        response = {
            "utr_head": {
                **{column.name: getattr(utr_head, column.name) for column in utr_head.__table__.columns},
                **format_dates(utr_head)
            },
            "labels": label,
            "utr_details": [{column.name: getattr(detail, column.name) for column in detail.__table__.columns} for detail in UTRDetail.query.filter_by(utrid=utr_id).all()]
        }

        return jsonify(response), 200

    except Exception as e:
        return jsonify({"error": "Internal server error", "message": str(e)}), 500

# Insert record for UTRHead and UTRDetail
@app.route(API_URL + "/insert-utr", methods=["POST"])
def insert_utr():
    tran_type = 'UT'
    def create_gledger_entry(data, amount, drcr, ac_code, accoid, drcrhead):
        return {
            "TRAN_TYPE": tran_type,
            "DOC_NO": new_doc_no,
            "DOC_DATE": data['doc_date'],
            "AC_CODE": ac_code,
            "AMOUNT": amount,
            "COMPANY_CODE": data['Company_Code'],
            "YEAR_CODE": data['Year_Code'],
            "ORDER_CODE": 1,
            "DRCR": drcr,
            "UNIT_Code": 0,
            "NARRATION": data['narration_header']+data['narration_footer'],
            "TENDER_ID": 0,
            "TENDER_ID_DETAIL": 0,
            "VOUCHER_ID": 0,
            "DRCR_HEAD": drcrhead,
            "ADJUSTED_AMOUNT": 0,
            "Branch_Code": 1,
            "SORT_TYPE": tran_type,
            "SORT_NO": new_doc_no,
            "vc": 0,
            "progid": 0,
            "tranid": 0,
            "saleid": 0,
            "ac": accoid
        }
    
    def add_gledger_entry(entries,data, amount, drcr, ac_code, accoid, drcrhead):
        if amount > 0:
            entries.append(create_gledger_entry(data, amount, drcr, ac_code, accoid, drcrhead))

    try:
        data = request.get_json()
        head_data = data['head_data']
        detail_data = data['detail_data']

        max_doc_no = db.session.query(func.max(UTRHead.doc_no)).scalar() or 0


        # Increment the doc_no for the new entry
        new_doc_no = max_doc_no + 1
        head_data['doc_no'] = new_doc_no 

        new_head = UTRHead(**head_data)
        db.session.add(new_head)


        createdDetails = []
        updatedDetails = []
        deletedDetailIds = []

        for item in detail_data:
            item['doc_no'] = new_doc_no
            item['utrid'] = new_head.utrid

            if 'rowaction' in item:
                if item['rowaction'] == "add":
                    del item['rowaction']
                    new_detail = UTRDetail(**item)
                    new_head.details.append(new_detail)
                    createdDetails.append(new_detail)

                elif item['rowaction'] == "update":
                    utrdetailid = item['utrdetailid']
                    update_values = {k: v for k, v in item.items() if k not in ('utrdetailid', 'rowaction', 'utrid')}
                    db.session.query(UTRDetail).filter(UTRDetail.utrdetailid == utrdetailid).update(update_values)
                    updatedDetails.append(utrdetailid)

                elif item['rowaction'] == "delete":
                    utrdetailid = item['utrdetailid']
                    detail_to_delete = db.session.query(UTRDetail).filter(UTRDetail.utrdetailid == utrdetailid).one_or_none()
                    if detail_to_delete:
                        db.session.delete(detail_to_delete)
                        deletedDetailIds.append(utrdetailid)

    

            db.session.commit()

            amount = float(head_data.get('amount', 0) or 0)

            bankAcCode = head_data.get('bank_ac')
            millCode = head_data.get('mill_code')

            

            gledger_entries = []


            if amount>0:
                
                accoid = get_accoid(bankAcCode,head_data['Company_Code'])
                add_gledger_entry(gledger_entries,head_data, amount, "C", bankAcCode, accoid , millCode)

                
                accoid = get_accoid(millCode,head_data['Company_Code'])
                add_gledger_entry(gledger_entries,head_data, amount, "D", millCode, accoid , bankAcCode)

            
            query_params = {
            'Company_Code': head_data['Company_Code'],
            'DOC_NO': new_doc_no,
            'Year_Code': head_data['Year_Code'],
            'TRAN_TYPE': tran_type,
        }

        response = requests.post("http://localhost:8080/api/sugarian/create-Record-gLedger", params=query_params, json=gledger_entries)

        if response.status_code == 201:
            db.session.commit()
        else:
            db.session.rollback()
            return jsonify({"error": "Failed to create gLedger record", "details": response.json()}), response.status_code

        utr_head_schema = UTRHeadSchema()
        utr_detail_schema = UTRDetailSchema(many=True)
            
        return jsonify({
            "message": "Data Inserted successfully",
            "head": utr_head_schema.dump(new_head),
            "addedDetails": utr_detail_schema.dump(createdDetails),
            "updatedDetails": updatedDetails,
            "deletedDetailIds": deletedDetailIds
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Internal server error", "message": str(e)}), 500

# Update record for UTRHead and UTRDetail
@app.route(API_URL + "/update-utr", methods=["PUT"])
def update_utr():
    
    tran_type = 'UT'
    def create_gledger_entry(data, amount, drcr, ac_code, accoid, drcrhead):
        return {
            "TRAN_TYPE": tran_type,
            "DOC_NO": updated_head_doc_no,
            "DOC_DATE": data['doc_date'],
            "AC_CODE": ac_code,
            "AMOUNT": amount,
            "COMPANY_CODE": data['Company_Code'],
            "YEAR_CODE": data['Year_Code'],
            "ORDER_CODE": 1,
            "DRCR": drcr,
            "UNIT_Code": 0,
            "NARRATION": data['narration_header']+data['narration_footer'],
            "TENDER_ID": 0,
            "TENDER_ID_DETAIL": 0,
            "VOUCHER_ID": 0,
            "DRCR_HEAD": drcrhead,
            "ADJUSTED_AMOUNT": 0,
            "Branch_Code": 1,
            "SORT_TYPE": tran_type,
            "SORT_NO": updated_head_doc_no,
            "vc": 0,
            "progid": 0,
            "tranid": 0,
            "saleid": 0,
            "ac": accoid
        }
    
    def add_gledger_entry(entries,data, amount, drcr, ac_code, accoid, drcrhead):
        if amount > 0:
            entries.append(create_gledger_entry(data, amount, drcr, ac_code, accoid, drcrhead))
    try:
        utrid = request.args.get('utrid')
        if not utrid:
            return jsonify({"error": "Missing 'utrid' parameter"}), 400

        data = request.get_json()
        head_data = data['head_data']
        detail_data = data['detail_data']

        # Update the head data
        updatedHeadCount=db.session.query(UTRHead).filter(UTRHead.utrid == utrid).update(head_data)
        updated_head = UTRHead.query.filter_by(utrid=utrid).first()
        updated_head_doc_no = updated_head.doc_no

        created_details = []
        updated_details = []
        deleted_detail_ids = []

        for item in detail_data:
            item['utrid'] = updated_head.utrid

            if 'rowaction' in item:
                if item['rowaction'] == "add":
                    del item['rowaction']
                    item['doc_no'] = updated_head_doc_no
                    new_detail = UTRDetail(**item)
                    db.session.add(new_detail)
                    created_details.append(new_detail)

                elif item['rowaction'] == "update":
                    utrdetailid = item['utrdetailid']
                    update_values = {k: v for k, v in item.items() if k not in ('utrdetailid', 'rowaction', 'utrid')}
                    db.session.query(UTRDetail).filter(UTRDetail.utrdetailid == utrdetailid).update(update_values)
                    updated_details.append(utrdetailid)

                elif item['rowaction'] == "delete":
                    utrdetailid = item['utrdetailid']
                    detail_to_delete = db.session.query(UTRDetail).filter(UTRDetail.utrdetailid == utrdetailid).one_or_none()
                    if detail_to_delete:
                        db.session.delete(detail_to_delete)
                        deleted_detail_ids.append(utrdetailid)

        db.session.commit()
        amount = float(head_data.get('amount', 0) or 0)

        bankAcCode = head_data.get('bank_ac')
        millCode = head_data.get('mill_code')

            

        gledger_entries = []


        if amount>0:
                
            accoid = get_accoid(bankAcCode,head_data['Company_Code'])
            add_gledger_entry(gledger_entries,head_data, amount, "C", bankAcCode, accoid , millCode)

                
            accoid = get_accoid(millCode,head_data['Company_Code'])
            add_gledger_entry(gledger_entries,head_data, amount, "D", millCode, accoid , bankAcCode)

            
        query_params = {
            'Company_Code': head_data['Company_Code'],
            'DOC_NO': updated_head_doc_no,
            'Year_Code': head_data['Year_Code'],
            'TRAN_TYPE': tran_type,
        }

        response = requests.post("http://localhost:8080/api/sugarian/create-Record-gLedger", params=query_params, json=gledger_entries)

        if response.status_code == 201:
            db.session.commit()
        else:
            db.session.rollback()
            return jsonify({"error": "Failed to create gLedger record", "details": response.json()}), response.status_code



        return jsonify({
            "message": "Data updated successfully",
            "head": updatedHeadCount,
            "created_details": utr_detail_schemas.dump(created_details),
            "updated_details": updated_details,
            "deleted_detail_ids": deleted_detail_ids
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Internal server error", "message": str(e)}), 500

# Delete record from database based on utrid
@app.route(API_URL + "/delete_data_by_utrid", methods=["DELETE"])
def delete_data_by_utrid():
    try:
        utrid = request.args.get('utrid')
        Company_Code = request.args.get('Company_Code')
        doc_no = request.args.get('doc_no')
        Year_Code = request.args.get('Year_Code')
        if not all([utrid, Company_Code, doc_no, Year_Code]):
            return jsonify({"error": "Missing required parameters"}), 400

        # Start a transaction
        with db.session.begin():
            # Delete records from UTRDetail table
            deleted_detail_rows = UTRDetail.query.filter_by(utrid=utrid,Company_Code=Company_Code,doc_no=doc_no,Year_Code=Year_Code).delete()

            # Delete record from UTRHead table
            deleted_head_rows = UTRHead.query.filter_by(utrid=utrid,Company_Code=Company_Code,doc_no=doc_no,Year_Code=Year_Code).delete()

            if deleted_detail_rows > 0 and deleted_head_rows > 0:
                query_params = {
                    'Company_Code': Company_Code,
                    'DOC_NO': doc_no,
                    'Year_Code': Year_Code,
                    'TRAN_TYPE': "UT",
            }

            # Make the external request
            response = requests.delete("http://localhost:8080/api/sugarian/delete-Record-gLedger", params=query_params)
            
            if response.status_code != 200:
                raise Exception("Failed to create record in gLedger")

        # Commit the transaction
        db.session.commit()

        return jsonify({
            "message": f"Deleted {deleted_head_rows} head row(s) and {deleted_detail_rows} detail row(s) successfully"
        }), 200

    except Exception as e:
        # Roll back the transaction if any error occurs
        db.session.rollback()
        return jsonify({"error": "Internal server error", "message": str(e)}), 500

# Fetch the last record from the database by utrid
@app.route(API_URL + "/get-lastutrdata", methods=["GET"])
def get_lastutrdata():
    try:
        Company_Code = request.args.get('Company_Code')
        Year_Code = request.args.get('Year_Code')
        if not all([Company_Code, Year_Code]):
            return jsonify({"error": "Missing required parameters"}), 400

        last_utr_head = UTRHead.query.order_by(UTRHead.doc_no.desc()).filter_by(Company_Code=Company_Code, Year_Code=Year_Code).first()
        if not last_utr_head:
            return jsonify({"error": "No records found in UTRHead table"}), 404

        utrid = last_utr_head.utrid
        additional_data = db.session.execute(text(UTR_DETAILS_QUERY), {"utrid": utrid})
        additional_data_row = additional_data.fetchone()

        label = dict(additional_data_row._mapping) if additional_data_row else {}

        last_head_data = {
            **{column.name: getattr(last_utr_head, column.name) for column in last_utr_head.__table__.columns},
            **format_dates(last_utr_head)
        }

        last_details_data = [{column.name: getattr(detail, column.name) for column in detail.__table__.columns} for detail in UTRDetail.query.filter_by(utrid=utrid).all()]

        response = {
            "last_head_data": last_head_data,
            "labels": label,
            "last_details_data": last_details_data
        }

        return jsonify(response), 200

    except Exception as e:
        return jsonify({"error": "Internal server error", "message": str(e)}), 500

# Get first record from the database
@app.route(API_URL + "/get-firstutr-navigation", methods=["GET"])
def get_firstutr_navigation():
    try:
        Company_Code = request.args.get('Company_Code')
        Year_Code = request.args.get('Year_Code')
        if not all([Company_Code, Year_Code]):
            return jsonify({"error": "Missing required parameters"}), 400

        first_utr_head = UTRHead.query.order_by(UTRHead.doc_no.asc()).filter_by(Company_Code=Company_Code, Year_Code=Year_Code).first()
        if not first_utr_head:
            return jsonify({"error": "No records found in UTRHead table"}), 404

        utrid = first_utr_head.utrid
        additional_data = db.session.execute(text(UTR_DETAILS_QUERY), {"utrid": utrid})
        additional_data_row = additional_data.fetchone()

        label = dict(additional_data_row._mapping) if additional_data_row else {}

        first_head_data = {
            **{column.name: getattr(first_utr_head, column.name) for column in first_utr_head.__table__.columns},
            **format_dates(first_utr_head)
        }

        first_details_data = [{column.name: getattr(detail, column.name) for column in detail.__table__.columns} for detail in UTRDetail.query.filter_by(utrid=utrid).all()]

        response = {
            "first_head_data": first_head_data,
            "labels": label,
            "first_details_data": first_details_data
        }

        return jsonify(response), 200

    except Exception as e:
        return jsonify({"error": "Internal server error", "message": str(e)}), 500

# Get previous record from the database
@app.route(API_URL + "/get-previousutr-navigation", methods=["GET"])
def get_previousutr_navigation():
    try:
        current_doc_no = request.args.get('currentDocNo')
        Company_Code = request.args.get('Company_Code')
        Year_Code = request.args.get('Year_Code')
        if not all([Company_Code, Year_Code, current_doc_no]):
            return jsonify({"error": "Missing required parameters"}), 400

        previous_utr_head = UTRHead.query.filter(UTRHead.doc_no < current_doc_no).filter_by(Company_Code=Company_Code, Year_Code=Year_Code).order_by(UTRHead.doc_no.desc()).first()
        if not previous_utr_head:
            return jsonify({"error": "No previous records found"}), 404

        utrid = previous_utr_head.utrid
        additional_data = db.session.execute(text(UTR_DETAILS_QUERY), {"utrid": utrid})
        additional_data_row = additional_data.fetchone()

        label = dict(additional_data_row._mapping) if additional_data_row else {}

        previous_head_data = {
            **{column.name: getattr(previous_utr_head, column.name) for column in previous_utr_head.__table__.columns},
            **format_dates(previous_utr_head)
        }

        previous_details_data = [{column.name: getattr(detail, column.name) for column in detail.__table__.columns} for detail in UTRDetail.query.filter_by(utrid=utrid).all()]

        response = {
            "previous_head_data": previous_head_data,
            "labels": label,
            "previous_details_data": previous_details_data
        }

        return jsonify(response), 200

    except Exception as e:
        return jsonify({"error": "Internal server error", "message": str(e)}), 500

# Get next record from the database
@app.route(API_URL + "/get-nextutr-navigation", methods=["GET"])
def get_nextutr_navigation():
    try:
        current_doc_no = request.args.get('currentDocNo')
        Company_Code = request.args.get('Company_Code')
        Year_Code = request.args.get('Year_Code')
        if not all([Company_Code, Year_Code, current_doc_no]):
            return jsonify({"error": "Missing required parameters"}), 400

        next_utr_head = UTRHead.query.filter(UTRHead.doc_no > current_doc_no).filter_by(Company_Code=Company_Code, Year_Code=Year_Code).order_by(UTRHead.doc_no.asc()).first()
        if not next_utr_head:
            return jsonify({"error": "No next records found"}), 404

        utrid = next_utr_head.utrid
        additional_data = db.session.execute(text(UTR_DETAILS_QUERY), {"utrid": utrid})
        additional_data_row = additional_data.fetchone()

        label = dict(additional_data_row._mapping) if additional_data_row else {}

        next_head_data = {
            **{column.name: getattr(next_utr_head, column.name) for column in next_utr_head.__table__.columns},
            **format_dates(next_utr_head)
        }

        next_details_data = [{column.name: getattr(detail, column.name) for column in detail.__table__.columns} for detail in UTRDetail.query.filter_by(utrid=utrid).all()]

        response = {
            "next_head_data": next_head_data,
            "labels": label,
            "next_details_data": next_details_data
        }

        return jsonify(response), 200

    except Exception as e:
        return jsonify({"error": "Internal server error", "message": str(e)}), 500
