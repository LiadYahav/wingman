import { NextRequest, NextResponse } from "next/server";

const PUBLIC_ROUTES = ["/login"];

export function proxy(req: NextRequest): NextResponse {
  const { pathname } = req.nextUrl;

  const isPublicRoute = PUBLIC_ROUTES.some((r) => pathname.startsWith(r));

  // Token stored as httpOnly cookie by the frontend after OAuth callback
  const token = req.cookies.get("wingman-token")?.value;

  if (!isPublicRoute && !token) {
    const loginUrl = new URL("/login", req.nextUrl);
    loginUrl.searchParams.set("redirect", pathname);
    return NextResponse.redirect(loginUrl);
  }

  // Already authenticated — don't let them hit /login again
  if (pathname === "/login" && token) {
    return NextResponse.redirect(new URL("/", req.nextUrl));
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    /*
     * Match all routes EXCEPT:
     * - /api/* (backend API — handled by nginx, shouldn't reach Next.js)
     * - /_next/static, /_next/image (Next.js internals)
     * - /favicon.ico, /wingman-logo.svg (static files)
     */
    "/((?!api|_next/static|_next/image|favicon.ico|.*\\.svg$|.*\\.png$).*)",
  ],
};
