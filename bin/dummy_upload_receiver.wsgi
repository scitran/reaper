# vim: filetype=python

def application(env, start_response):
    env['wsgi.input'].read()
    start_response('200 OK', [('Content-Type','text/html')])
    return []
