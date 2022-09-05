import importlib

class DeskCore:
    def __init__(self,plugins:list=[]):

        # init default plugin
        self._plugins = [importlib.import_module('default',".").Plugin()]
        
        # append plugin list
        if plugins != []:
            for plugin in plugins:
                self._plugins.append(importlib.import_module(plugin,".").Plugin())
            

    def run(self):
        print("Start my app")
        print("-" * 10)
        print("This is my core system")

        for plugin in self._plugins:
            plugin.process(5,3)

        print("-" * 10)
        print("End my app")