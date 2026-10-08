import json, os, random, secrets, socket, threading, time, io
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path
import qrcode
ROOT=Path(__file__).parent
QUESTIONS=json.loads((ROOT/'questions.json').read_text(encoding='utf-8'))
LOCK=threading.RLock()
PIN=str(random.SystemRandom().randint(1000,9999))
ADMIN=secrets.token_urlsafe(22)
STATE={'phase':'lobby','index':-1,'deadline':0,'players':{},'reveal':False}
DURATION=30

def public_state(admin=False, token=None):
    with LOCK:
        idx=STATE['index']; q=QUESTIONS[idx] if 0<=idx<len(QUESTIONS) else None
        players=sorted([{'id':k,'nick':v['nick'],'avatar':v['avatar'],'score':v['score'],'answered':idx in v['answers']} for k,v in STATE['players'].items()],key=lambda x:-x['score'])
        out={'phase':STATE['phase'],'index':idx,'total':len(QUESTIONS),'deadline':STATE['deadline'],'serverTime':time.time(),'players':players,'reveal':STATE['reveal']}
        if q:out['question']={'text':q['text'],'answers':q['answers']}
        if STATE['reveal'] and q:out['correct']=q['correct']
        if token in STATE['players'] and idx>=0:out['myAnswer']=STATE['players'][token]['answers'].get(idx)
        return out
class Handler(BaseHTTPRequestHandler):
    def send(self,code,data,typ='application/json; charset=utf-8'):
        raw=data if isinstance(data,bytes) else (json.dumps(data,ensure_ascii=False).encode() if typ.startswith('application/json') else data.encode())
        self.send_response(code);self.send_header('Content-Type',typ);self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(raw)
    def body(self):
        try:return json.loads(self.rfile.read(min(int(self.headers.get('Content-Length','0')),8192)))
        except:return {}
    def do_GET(self):
        u=urlparse(self.path);params=parse_qs(u.query)
        if u.path=='/':return self.send(200,(ROOT/'index.html').read_text(encoding='utf-8'),'text/html; charset=utf-8')
        if u.path=='/api/state':return self.send(200,public_state(token=params.get('token',[None])[0]))
        if u.path=='/api/host':
            if params.get('key',[''])[0]!=ADMIN:return self.send(403,{'error':'Acesso negado'})
            return self.send(200,{'pin':PIN,'state':public_state()})
        if u.path=='/qr.png':
            url=f'http://{self.headers.get("Host", "localhost:8000")}/?join=1'
            img=qrcode.make(url);b=io.BytesIO();img.save(b,format='PNG');return self.send(200,b.getvalue(),'image/png')
        return self.send(404,{'error':'Não encontrado'})
    def do_POST(self):
        u=urlparse(self.path);d=self.body()
        with LOCK:
            if u.path=='/api/join':
                if str(d.get('pin',''))!=PIN:return self.send(403,{'error':'PIN incorreto'})
                if STATE['phase']!='lobby':return self.send(409,{'error':'Partida já iniciada'})
                nick=str(d.get('nick','')).strip()[:24];avatar=str(d.get('avatar',''))[:8]
                if not nick or not avatar:return self.send(400,{'error':'Escolha apelido e avatar'})
                if any(p['nick'].casefold()==nick.casefold() for p in STATE['players'].values()):return self.send(409,{'error':'Apelido em uso'})
                token=secrets.token_urlsafe(20);STATE['players'][token]={'nick':nick,'avatar':avatar,'score':0,'answers':{}}
                return self.send(200,{'token':token})
            if u.path=='/api/answer':
                token=d.get('token');idx=STATE['index'];p=STATE['players'].get(token)
                if not p:return self.send(403,{'error':'Participante não encontrado'})
                if STATE['phase']!='question' or time.time()>STATE['deadline'] or idx in p['answers']:return self.send(409,{'error':'Resposta encerrada ou já enviada'})
                choice=d.get('choice')
                if type(choice)!=int or choice not in range(4):return self.send(400,{'error':'Alternativa inválida'})
                p['answers'][idx]=choice
                if choice==QUESTIONS[idx]['correct']:p['score']+=100+max(0,int((STATE['deadline']-time.time())/DURATION*100))
                return self.send(200,{'ok':True})
            if d.get('key')!=ADMIN:return self.send(403,{'error':'Acesso de professor negado'})
            if u.path=='/api/next':
                if STATE['phase']=='question':STATE['reveal']=True;STATE['phase']='reveal'
                elif STATE['index']+1>=len(QUESTIONS):STATE['phase']='finished'
                else:STATE['index']+=1;STATE['phase']='question';STATE['reveal']=False;STATE['deadline']=time.time()+DURATION
                return self.send(200,{'ok':True})
            if u.path=='/api/reset':
                STATE.update(phase='lobby',index=-1,deadline=0,players={},reveal=False)
                return self.send(200,{'ok':True})
        return self.send(404,{'error':'Não encontrado'})
    def log_message(self,*args):pass

def ip():
    s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    try:s.connect(('192.0.2.1',80));return s.getsockname()[0]
    except:return '127.0.0.1'
    finally:s.close()
if __name__=='__main__':
    port=int(os.environ.get('PORT','8000'))
    print('\nQUIZ BASES DE DADOS\nAcesso professor: http://localhost:%d/?host=%s\nAcesso alunos: http://%s:%d/\nPIN: %s\n'%(port,ADMIN,ip(),port,PIN),flush=True)
    ThreadingHTTPServer(('0.0.0.0',port),Handler).serve_forever()
