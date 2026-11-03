interface Env { HF_SPACE_URL: string }
export const onRequest = async ({request, env}: {request: Request; env: Env}) => {
  if (!env.HF_SPACE_URL) return Response.json({detail:'Backend URL is not configured'},{status:503});
  const original = new URL(request.url);
  const upstream = new URL(original.pathname + original.search, env.HF_SPACE_URL);
  if (upstream.protocol !== 'https:') return Response.json({detail:'Backend must use HTTPS'},{status:500});
  const headers = new Headers(request.headers);
  headers.delete('cookie'); headers.delete('authorization');
  const response = await fetch(upstream, {method:request.method, headers, body:request.body, redirect:'manual'});
  const safe = new Headers(response.headers);safe.delete('set-cookie');
  return new Response(response.body,{status:response.status,headers:safe});
};
