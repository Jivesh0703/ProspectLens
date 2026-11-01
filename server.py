"""Production HTTP surface for AccountBrief; research logic stays in app.py."""
from __future__ import annotations
import base64
import binascii
import datetime as dt
import hmac
import os
import threading
from urllib.parse import urlsplit
from flask import Flask, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix
import app as core


class ResearchGate:
    """Single active research run and a per-process UTC-day attempt allowance."""
    def __init__(self, daily_limit):
        self.busy=threading.BoundedSemaphore(1)
        self.daily_limit=daily_limit
        self.day=dt.datetime.now(dt.timezone.utc).date()
        self.used=0
    def begin(self):
        if not self.busy.acquire(blocking=False):
            return 'Research is already running. Please try again shortly.',15
        today=dt.datetime.now(dt.timezone.utc).date()
        if today!=self.day:
            self.day=today;self.used=0
        if self.daily_limit and self.used>=self.daily_limit:
            self.busy.release()
            return 'The daily research allowance has been reached. Please try again tomorrow.',3600
        self.used+=1
        return None,None
    def end(self):
        self.busy.release()


def create_app(settings=None, research_runner=None):
    if settings is None:
        core.load_env()
        settings=dict(os.environ)
    else:
        settings=dict(settings)
    on_render=settings.get('RENDER','').lower()=='true'
    production=on_render or settings.get('APP_ENV')=='production'
    username=settings.get('ACCESS_USERNAME','reviewer')
    password=settings.get('ACCESS_PASSWORD','')
    if production and (not username or len(password)<12):
        raise ValueError('Production requires ACCESS_USERNAME and ACCESS_PASSWORD (at least 12 characters).')
    if production and not settings.get('GEMINI_API_KEY','').strip():
        raise ValueError('Production requires GEMINI_API_KEY.')
    try:
        daily_limit=int(settings.get('MAX_DAILY_RESEARCH','20' if production else '0'))
        rpm=int(settings.get('GEMINI_RPM','5'))
        if daily_limit<0 or (production and daily_limit==0) or not 1<=rpm<=60:
            raise ValueError()
    except ValueError:
        raise ValueError('Set a positive production MAX_DAILY_RESEARCH and GEMINI_RPM from 1 to 60.')
    explicit_origin=settings.get('APP_ORIGIN','').rstrip('/')
    render_origin=settings.get('RENDER_EXTERNAL_URL','').rstrip('/')
    render_host=settings.get('RENDER_EXTERNAL_HOSTNAME','')
    origins=set()
    hosts=set()
    for origin in (explicit_origin,render_origin):
        if origin:
            parsed=urlsplit(origin)
            if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password or parsed.path not in ('','/') or parsed.query or parsed.fragment or (production and parsed.scheme!='https'):
                raise ValueError('APP_ORIGIN/RENDER_EXTERNAL_URL must be a public HTTPS origin without a path in production.')
            origins.add(origin);hosts.add(parsed.hostname)
    if render_host:
        if '/' in render_host or ':' in render_host or not render_host.strip():
            raise ValueError('Invalid RENDER_EXTERNAL_HOSTNAME.')
        hosts.add(render_host)
        origins.add('https://'+render_host)
    if production and not hosts:
        raise ValueError('Production requires Render hostname metadata or APP_ORIGIN.')
    if not production:
        hosts.update(('localhost','127.0.0.1','[::1]'))
    web=Flask(__name__,static_folder=None)
    web.config.update(MAX_CONTENT_LENGTH=12000,TRUSTED_HOSTS=sorted(hosts),PRODUCTION=production,ON_RENDER=on_render)
    if on_render:
        # Render supplies the last X-Forwarded-Proto value. Do not trust forwarded Host/IP.
        web.wsgi_app=ProxyFix(web.wsgi_app,x_for=0,x_proto=1,x_host=0,x_port=0,x_prefix=0)
    gate=ResearchGate(daily_limit)
    web.extensions['research_gate']=gate
    runner=research_runner or core.run

    @web.before_request
    def require_access():
        if request.path=='/api/health' and request.method in ('GET','HEAD'):
            return None
        if not password:
            return None
        header=request.headers.get('Authorization','')
        valid=False
        try:
            scheme,token=header.split(' ',1)
            if scheme.lower()=='basic':
                decoded=base64.b64decode(token,validate=True).decode('utf-8')
                user,secret=decoded.split(':',1)
                valid=hmac.compare_digest(user.encode(),username.encode()) & hmac.compare_digest(secret.encode(),password.encode())
        except (ValueError,UnicodeError,binascii.Error):
            pass
        if not valid:
            response=jsonify(error='Sign in to access AccountBrief.')
            response.status_code=401
            response.headers['WWW-Authenticate']='Basic realm="AccountBrief", charset="UTF-8"'
            return response
        return None

    @web.after_request
    def response_headers(response):
        response.headers['Cache-Control']='no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['X-Frame-Options']='DENY'
        response.headers['Referrer-Policy']='same-origin'
        response.headers['Content-Security-Policy']="default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        if production and request.is_secure:
            response.headers['Strict-Transport-Security']='max-age=86400'
        return response

    @web.get('/api/health')
    def health():
        return jsonify(ok=True)

    @web.get('/')
    def index():
        return send_from_directory(core.ROOT/'static','index.html')

    @web.get('/app.js')
    def javascript():
        return send_from_directory(core.ROOT/'static','app.js')

    @web.get('/style.css')
    def stylesheet():
        return send_from_directory(core.ROOT/'static','style.css')

    @web.post('/api/research')
    def research():
        if request.headers.get('Sec-Fetch-Site')=='cross-site':
            return jsonify(error='Cross-site requests are blocked.'),403
        origin=request.headers.get('Origin')
        allowed=origins if production else {request.host_url.rstrip('/')}
        if origin and origin not in allowed:
            return jsonify(error='Origin mismatch.'),403
        if not request.is_json:
            return jsonify(error='Send an application/json request.'),415
        try:
            data=request.get_json()
            core.validate_input(data)
        except (core.InputError,ValueError) as exc:
            return jsonify(error=str(exc)),400
        message,retry_after=gate.begin()
        if message:
            response=jsonify(error=message);response.status_code=429
            response.headers['Retry-After']=str(retry_after)
            return response
        try:
            return jsonify(runner(data))
        except core.InputError as exc:
            return jsonify(error=str(exc)),400
        except Exception:
            # Standard exception logging excludes request payloads, headers and environment values.
            web.logger.exception('Account research failed')
            return jsonify(error='Research could not be completed. Please try again shortly.'),500
        finally:
            gate.end()

    @web.errorhandler(HTTPException)
    def http_error(error):
        messages={400:'Invalid request.',404:'Not found.',405:'Method not allowed.',413:'Request exceeds the 12 KB limit.'}
        return jsonify(error=messages.get(error.code,'Request could not be processed.')),error.code
    return web


def serve_app(web,host,port):
    from waitress import serve
    serve(web,host=host,port=port,threads=4,connection_limit=64,
          max_request_body_size=12000,max_request_header_size=16384,
          channel_timeout=240,expose_tracebacks=False,
          # Let only the explicitly configured ProxyFix consume Render's proto header.
          clear_untrusted_proxy_headers=not web.config['ON_RENDER'])
