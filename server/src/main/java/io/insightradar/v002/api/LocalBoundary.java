package io.insightradar.v002.api;
import jakarta.servlet.*;
import jakarta.servlet.http.*;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;
import java.io.IOException;
import java.util.Set;
/** Origin/Host guard matters even without authentication: deny browser cross-site writes. */
@Component
public class LocalBoundary extends OncePerRequestFilter {
 private static final Set<String> ORIGINS=Set.of("http://127.0.0.1:15173","http://localhost:15173","http://127.0.0.1:18080","http://localhost:18080");
 @Override protected void doFilterInternal(HttpServletRequest req,HttpServletResponse res,FilterChain chain)throws ServletException,IOException{
  res.setHeader("X-Content-Type-Options","nosniff");res.setHeader("X-Frame-Options","DENY");res.setHeader("Referrer-Policy","no-referrer");res.setHeader("Cache-Control","no-store");
  if(!Set.of("127.0.0.1","localhost","::1","[::1]").contains(req.getServerName())){res.sendError(403);return;}
  String origin=req.getHeader("Origin");if(origin!=null&&!ORIGINS.contains(origin)){res.sendError(403);return;}
  if(origin!=null){res.setHeader("Access-Control-Allow-Origin",origin);res.setHeader("Vary","Origin");res.setHeader("Access-Control-Allow-Methods","GET,POST,PUT,OPTIONS");res.setHeader("Access-Control-Allow-Headers","Content-Type");}
  if(req.getMethod().equals("OPTIONS")){res.setStatus(204);return;}chain.doFilter(req,res);
 }
}
