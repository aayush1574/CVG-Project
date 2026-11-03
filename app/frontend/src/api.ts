const transient = new Set([502,503,504]);
export async function apiFetch(url:string,init:RequestInit={}):Promise<Response>{
  for(let attempt=0;attempt<2;attempt++){
    const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),90000);
    try{
      const response=await fetch(url,{...init,signal:controller.signal});
      if(attempt===0&&transient.has(response.status)){await response.body?.cancel();await new Promise(resolve=>setTimeout(resolve,1500));continue}
      return response;
    }catch(error){if(attempt===1)throw error;await new Promise(resolve=>setTimeout(resolve,1500))}
    finally{clearTimeout(timer)}
  }
  throw new Error('AI engine is warming up. Please try again shortly.');
}
