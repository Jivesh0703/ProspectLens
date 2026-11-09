"""User-authorized Salesforce OAuth and reviewed account activity creation."""
import base64
import datetime as dt
import hashlib
import json
import re
import secrets
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from flask import jsonify, redirect, request, session


def salesforce_request(url, data=None, headers=None, form=False):
    body=None if data is None else (urlencode(data).encode() if form else json.dumps(data).encode())
    req=Request(url,data=body,headers={'Content-Type':'application/x-www-form-urlencoded' if form else 'application/json',**(headers or {})})
    with urlopen(req,timeout=20) as response:
        return json.load(response)


def task_payload(data):
    if not isinstance(data,dict) or data.get('reviewed') is not True:
        raise ValueError('Review the evidence and draft before saving to Salesforce.')
    account_id=data.get('account_id','')
    if not isinstance(account_id,str) or not re.fullmatch(r'001[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?',account_id):
        raise ValueError('Enter a Salesforce Account ID of 15 or 18 characters, starting with 001.')
    brief=data.get('brief')
    if not isinstance(brief,dict) or brief.get('service_error') or not brief.get('outreach_draft'):
        raise ValueError('A completed brief with an outreach draft is required.')
    evidence=brief.get('evidence')
    if not isinstance(evidence,list) or not 1<=len(evidence)<=8:
        raise ValueError('Include the reviewed source evidence.')
    lines=[]
    for item in evidence:
        if not isinstance(item,dict) or not all(isinstance(item.get(k),str) for k in ('id','quote','source_url')):
            raise ValueError('Invalid source evidence.')
        if urlsplit(item['source_url']).scheme not in ('http','https'):
            raise ValueError('Evidence needs public website links.')
        lines.append(f"[{item['id']}] {item['quote']}\n{item['source_url']}")
    for key in ('account','hypothesis','outreach_draft'):
        if not isinstance(brief.get(key),str):
            raise ValueError('The brief is incomplete.')
    description='ProspectLens research reviewed by user\n\nEvidence\n'+'\n\n'.join(lines)+'\n\nDiscovery question\n'+brief['hypothesis']+'\n\nOutreach draft\n'+brief['outreach_draft']
    if len(description)>30000:
        raise ValueError('The brief exceeds Salesforce task text limits.')
    return {'WhatId':account_id,'Subject':('ProspectLens research: '+brief['account'])[:255], 'Description':description,'Status':'Completed','Priority':'Normal'}


def register_salesforce(web,settings,origins):
    client_id=settings.get('SALESFORCE_CLIENT_ID','').strip()
    secret=settings.get('SALESFORCE_CLIENT_SECRET','').strip()
    session_secret=settings.get('SESSION_SECRET','')
    enabled=bool(client_id and secret and len(session_secret)>=32)
    login=settings.get('SALESFORCE_LOGIN_URL','https://login.salesforce.com').rstrip('/')
    if login not in ('https://login.salesforce.com','https://test.salesforce.com'):
        raise ValueError('SALESFORCE_LOGIN_URL must be https://login.salesforce.com or https://test.salesforce.com.')
    web.config.update(SECRET_KEY=session_secret or None,SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SECURE=web.config['PRODUCTION'],SESSION_COOKIE_SAMESITE='Lax',PERMANENT_SESSION_LIFETIME=dt.timedelta(hours=1))

    @web.get('/api/salesforce/status')
    def status():
        return jsonify(configured=enabled,connected=enabled and bool(session.get('sf_token')))

    @web.get('/api/salesforce/connect')
    def connect():
        if not enabled:
            return jsonify(error='Configure Salesforce OAuth credentials and a SESSION_SECRET of at least 32 characters.'),503
        callback=request.host_url.rstrip('/')+'/api/salesforce/callback'
        if web.config['PRODUCTION'] and request.host_url.rstrip('/') not in origins:
            return jsonify(error='Configure APP_ORIGIN for this deployment domain.'),400
        state=secrets.token_urlsafe(32)
        verifier=secrets.token_urlsafe(48)
        session['sf_oauth']={'state':state,'verifier':verifier,'callback':callback,'created':time.time()}
        challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
        return redirect(login+'/services/oauth2/authorize?'+urlencode({'response_type':'code','client_id':client_id,'redirect_uri':callback,'scope':'api','state':state,'code_challenge':challenge,'code_challenge_method':'S256'}))

    @web.get('/api/salesforce/callback')
    def callback():
        oauth=session.pop('sf_oauth',None)
        if not enabled or not oauth or time.time()-oauth['created']>600 or not secrets.compare_digest(request.args.get('state',''),oauth['state']):
            return jsonify(error='Salesforce authorization expired or state did not match. Connect again.'),400
        code=request.args.get('code')
        if not code:
            return redirect('/?salesforce=denied')
        try:
            token=salesforce_request(login+'/services/oauth2/token',{'grant_type':'authorization_code','code':code,'client_id':client_id,'client_secret':secret,'redirect_uri':oauth['callback'],'code_verifier':oauth['verifier']},form=True)
            instance=token.get('instance_url','').rstrip('/')
            if not re.fullmatch(r'https://[A-Za-z0-9.-]+\.salesforce\.com',instance) or not isinstance(token.get('access_token'),str) or not token['access_token']:
                raise ValueError('Invalid Salesforce token response.')
            session.clear()
            session.permanent=True
            session['sf_token']=token['access_token']
            session['sf_instance']=instance
        except (HTTPError,URLError,OSError,ValueError,TypeError):
            return redirect('/?salesforce=failed')
        return redirect('/?salesforce=connected')

    def same_origin():
        return request.headers.get('Origin')==request.host_url.rstrip('/') and request.headers.get('Sec-Fetch-Site')!='cross-site'

    @web.post('/api/salesforce/disconnect')
    def disconnect():
        if not same_origin():
            return jsonify(error='Origin mismatch.'),403
        session.clear()
        return jsonify(connected=False)

    @web.get('/api/salesforce/accounts')
    def accounts():
        if request.headers.get('Sec-Fetch-Site')=='cross-site':
            return jsonify(error='Cross-site requests are blocked.'),403
        if not enabled or not session.get('sf_token'):
            return jsonify(error='Connect Salesforce to search your accounts.'),401
        term=request.args.get('q','').strip()
        if not 2<=len(term)<=120 or any(ord(char)<32 for char in term):
            return jsonify(error='Search with a company name or website of 2–120 characters.'),400
        # Escape both SOQL string delimiters and LIKE wildcards as literal input.
        escaped=term.replace('\\','\\\\').replace("'","\\'").replace('%','\\%').replace('_','\\_')
        pattern="'%"+escaped+"%'"
        query='SELECT Id, Name, Website FROM Account WHERE Name LIKE '+pattern+' OR Website LIKE '+pattern+' ORDER BY Name LIMIT 20'
        try:
            response=salesforce_request(session['sf_instance']+'/services/data/v61.0/query?'+urlencode({'q':query}),headers={'Authorization':'Bearer '+session['sf_token']})
            records=response.get('records')
            if not isinstance(records,list):
                raise ValueError('Invalid account response.')
            matches=[]
            for record in records[:20]:
                if not isinstance(record,dict) or not re.fullmatch(r'001[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?',str(record.get('Id',''))) or not isinstance(record.get('Name'),str):
                    raise ValueError('Invalid account record.')
                matches.append({'id':record['Id'],'name':record['Name'],'website':record.get('Website') or ''})
            return jsonify(accounts=matches,create_url=session['sf_instance']+'/lightning/o/Account/new')
        except HTTPError as exc:
            if exc.code==401:
                session.clear()
                return jsonify(error='Salesforce session expired. Connect again.'),401
            return jsonify(error='Salesforce account search failed. Check Account read permissions and API access.'),502
        except (URLError,OSError,ValueError,TypeError):
            return jsonify(error='Could not search Salesforce accounts. Please try again.'),502

    @web.post('/api/salesforce/save')
    def save():
        if not same_origin():
            return jsonify(error='Origin mismatch.'),403
        if not enabled or not session.get('sf_token'):
            return jsonify(error='Connect Salesforce before saving a brief.'),401
        if not request.is_json:
            return jsonify(error='Send an application/json request.'),415
        try:
            payload=task_payload(request.get_json())
        except (ValueError,TypeError) as exc:
            return jsonify(error=str(exc)),400
        try:
            result=salesforce_request(session['sf_instance']+'/services/data/v61.0/sobjects/Task',payload,{'Authorization':'Bearer '+session['sf_token']})
            if not result.get('success') or not re.fullmatch(r'00T[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?',result.get('id','')):
                raise ValueError('Unexpected task response.')
            return jsonify(id=result['id'],url=session['sf_instance']+'/'+result['id']),201
        except HTTPError as exc:
            if exc.code==401:
                session.clear()
                return jsonify(error='Salesforce session expired. Connect again.'),401
            return jsonify(error='Salesforce rejected the task. Check Account ID, task permissions, and required custom fields.'),502
        except (URLError,OSError,ValueError,TypeError):
            return jsonify(error='Save outcome is uncertain. Check the account activity in Salesforce before saving again.'),502
