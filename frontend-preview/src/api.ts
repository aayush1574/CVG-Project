export async function api<T>(path:string, init:RequestInit={}, signal?:AbortSignal):Promise<T>{
  for(let attempt=0;attempt<2;attempt++){
    const controller=new AbortController();
    const abort=()=>controller.abort();
    signal?.addEventListener('abort',abort,{once:true});
    if(signal?.aborted)controller.abort();
    const timer=setTimeout(abort,90000);
    try{
      const response=await fetch(path,{...init,signal:controller.signal});
      if(attempt===0&&[502,503,504].includes(response.status)){await response.body?.cancel();continue;}
      const body=await response.json().catch(()=>({detail:'The engine returned an unreadable response.'}));
      if(!response.ok)throw new Error(typeof body.detail==='string'?body.detail:JSON.stringify(body.detail));
      return body as T;
    }catch(error){if(signal?.aborted)throw new DOMException('Cancelled','AbortError');if(attempt===0&&(error instanceof TypeError||(error instanceof DOMException&&error.name==='AbortError')))continue;throw error;}
    finally{clearTimeout(timer);signal?.removeEventListener('abort',abort);}
  }
  throw new Error('Engine temporarily unavailable. Please retry.');
}
export async function apiFetch(path:string,init:RequestInit={}){
 const body=await api(path,init,init.signal??undefined);
 return new Response(JSON.stringify(body),{headers:{'content-type':'application/json'}});
}
