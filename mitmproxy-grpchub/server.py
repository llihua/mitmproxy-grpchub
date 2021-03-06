'''
Created on 2020年12月6日

@author: stephen
'''
from concurrent import futures
import uuid
import base64
import time
import grpc
import threading
import traceback
import asyncio
import mitm_hub_pb2
import mitm_hub_pb2_grpc

from mitmproxy import proxy, options
from mitmproxy.tools.dump import DumpMaster
from mitmproxy.script import concurrent
from mitmproxy import flowfilter
from mitmproxy import ctx, http

from mitmproxy.addons import upstream_auth

from mitm_flow_callback import MitmproxyFlower

# 实现 proto 文件中定义的 MitmProxyHubServerServicer
class BothwayMitmServer(mitm_hub_pb2_grpc.MitmProxyHubServerServicer):
    def __init__(self):
        self.mitmproxies = {}
        self.locker = threading.Lock()

    def startDumpMaster(self, bind="0.0.0.0", port=8866, mitmproxyId = str(uuid.uuid4()), callbackServerAddr = None, callbackServerPort = None, upstream = None, upstreamAuth = None):
        print("start........", bind, port)
        # see source mitmproxy/master.py for details
        loop =  asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        opts = options.Options(listen_host=bind, listen_port=port)
        #upstream = "http://http-dyn.abuyun.com:9020"
        #upstreamAuth = "H88QO221HIVO10MD:62769571795BDB48"
        if upstream:
            opts.add_option("mode", str, "upstream:" + upstream, "")#设置上游代理
            print("set upstream", upstream)
        opts.add_option("ssl_insecure", bool, True, "")#不验证上游代理证书
        # pconf = proxy.config.ProxyConfig(opts)
        # mDumpMaster = DumpMaster(opts)
        # mDumpMaster.server = proxy.server.ProxyServer(pconf)
        mDumpMaster = DumpMaster(
            opts,
            with_termlog=False,
            with_dumper=False,
        )
        
        try:
            self.locker.acquire()
            self.mitmproxies[mitmproxyId] = mDumpMaster
            print("save mitmproxies", mitmproxyId)
        finally:
            self.locker.release()
        if upstream and upstreamAuth: #坑啊
            upstreamAuthAddon:upstream_auth.UpstreamAuth = mDumpMaster.addons.get("upstreamauth")
            upstreamAuthAddon.auth = upstream_auth.parse_upstream_auth(upstreamAuth)
            print("set upstreamAuth", upstreamAuthAddon.auth)
        mDumpMaster.addons.add(MitmproxyFlower(callbackServerAddr, callbackServerPort, mitmproxyId))

        # mDumpMaster.run() #is blocking
        mDumpMaster.run_loop(loop.run_forever)
        # run mitmproxy in backgroud, especially integrated with other server
        # loop = asyncio.get_event_loop()
        # t = threading.Thread( target=loop_in_thread, args=(loop,mDumpMaster) )
        # t.start()



        print("finished mitmproxy", mitmproxyId)
    
    def start(self, request, context):
        """Missing associated documentation comment in .proto file."""
        bind = request.bind
        port = request.port
        mitmproxyId = str(uuid.uuid4())
        callbackServerAddr = request.callbackServerAddr
        callbackServerPort = request.callbackServerPort
        upstream = request.upstream
        upstreamAuth = request.upstreamAuth
        thead_one = threading.Thread(target=self.startDumpMaster, args=(bind, port, mitmproxyId, callbackServerAddr, callbackServerPort, upstream, upstreamAuth))
        thead_one.start()
        return mitm_hub_pb2.MitmproxyStartResponse(mitmproxyId=mitmproxyId)
    
    def stop(self, request, context):
        """Missing associated documentation comment in .proto file."""
        mitmproxyId = request.mitmproxyId
        mDumpMaster:DumpMaster = self.mitmproxies.get(mitmproxyId)
        try:
            self.locker.acquire()
            if mDumpMaster:
                del self.mitmproxies[mitmproxyId]
                print("del mitmproxies", mitmproxyId)
                mDumpMaster.shutdown()
        except:
            traceback.print_exc()
        finally:
            self.locker.release()
        raise mitm_hub_pb2.VoidResponse()

async def serve():    
    def loop_in_thread():
        time.sleep(1)
        #loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)  #_set_running_loop
        # m.run_loop(loop.run_forever)
        l = asyncio.get_running_loop()
        if not l:
            pass
        time.sleep(10)

    # # loop = asyncio.new_event_loop()
    # loop = asyncio.get_event_loop()
    # m = 1
    # #await asyncio.to_thread(loop_in_thread)
    # t = threading.Thread( target=loop_in_thread, args=(loop, m) )
    # t.start()
    # time.sleep(10)
    # m = 2
    # time.sleep(10)

    # 启动 rpc 服务
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=100))
    mitm_hub_pb2_grpc.add_MitmProxyHubServerServicer_to_server(BothwayMitmServer(), server)
    server.add_insecure_port('[::]:60051')
    print("serve on 0.0.0.0:60051")
    server.start()
    try:
        while True:
            time.sleep(1) # one day in seconds
    except KeyboardInterrupt:
        server.stop(0)

if __name__ == '__main__':
    #serve() #asyncio.run(serve())
    loop = asyncio.get_event_loop()
    loop.run_until_complete(asyncio.wait([serve()]))
    loop.close()

