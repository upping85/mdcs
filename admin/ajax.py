################################################################################
#
# File Name: ajax.py
# Application: admin
# Purpose:    AJAX methods used for administration purposes
#
# Author: Sharief Youssef
#         sharief.youssef@nist.gov
#
#         Guillaume SOUSA AMARAL
#         guillaume.sousa@nist.gov
#
# Sponsor: National Institute of Standards and Technology (NIST)
#
################################################################################

from dajax.core import Dajax
from dajaxice.decorators import dajaxice_register
import lxml.html as html
import lxml.etree as etree
import json
from io import BytesIO
from mgi.models import Template, TemplateVersion, Instance, Request, Module, ModuleResource, Type, TypeVersion, Message, TermsOfUse, PrivacyPolicy, Bucket, MetaSchema
import requests
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
import os
from django.conf import settings
from datetime import datetime
import mgi
from _io import StringIO
from utils.XSDflattenerMDCS.XSDflattenerMDCS import XSDFlattenerMDCS
# from utils.XSDflattener.XSDflattener import XSDFlattenerURL
from utils.XSDhash import XSDhash
from utils.APIschemaLocator import APIschemaLocator
import random
from utils.APIschemaLocator.APIschemaLocator import getSchemaLocation
from mgi import utils

#Class definition

################################################################################
# 
# Class Name: ModuleResourceInfo
#
# Description: Store information about a resource for a module
#
################################################################################
class ModuleResourceInfo:
    "Class that store information about a resource for a module"
    
    def __init__(self, content = "", filename = ""):
        self.content = content
        self.filename = filename   

    def __to_json__(self):
        return json.dumps(self, default=lambda o:o.__dict__)


################################################################################
# 
# Function Name: uploadObject(request,objectName,objectFilename,objectContent, objectType)
# Inputs:        request - 
#                objectName - 
#                objectFilename - 
#                objectContent -
#                objectType -
# Outputs:       JSON data 
# Exceptions:    None
# Description:   Upload of an object (template or type)
# 
################################################################################
@dajaxice_register
def uploadObject(request,objectName,objectFilename,objectContent, objectType):
    print 'BEGIN def uploadObject(request,objectName,objectFilename,objectContent, objectType)'
    dajax = Dajax()
    
    # Save all parameters
    request.session['uploadObjectName'] = objectName
    request.session['uploadObjectFilename'] = objectFilename
    request.session['uploadObjectContent'] = objectContent
    request.session['uploadObjectType'] = objectType
    
    request.session['uploadObjectValid'] = False
    
    xmlTree = None

    # is it a valid XML document ?
    try:            
        xmlTree = etree.parse(BytesIO(objectContent.encode('utf-8')))
    except Exception, e:
        dajax.script("""$("#objectUploadErrorMessage").html("<font color='red'>Not a valid XML document.</font><br/>"""+e.message.replace("'","") +""" ");""")
        return dajax.json()
    
    # is it supported by the MDCS ?
    errors = utils.getValidityErrorsForMDCS(xmlTree, objectType)
    if len(errors) > 0:
        errorsStr = ""
        for error in errors:
            errorsStr += error + "<br/>"
        dajax.script("""$("#objectUploadErrorMessage").html("<font color='red'>"""+ errorsStr +"""</font>");""")
        return dajax.json() 
    
    # get the imports
    imports = xmlTree.findall("{http://www.w3.org/2001/XMLSchema}import")
    # get the includes
    includes = xmlTree.findall("{http://www.w3.org/2001/XMLSchema}include")
    
    if len(imports) != 0 or len(includes) != 0:
        # Display array to resolve dependencies
        htmlString = generateHtmlDependencyResolver(imports, includes)
        dajax.script("""$("#objectUploadErrorMessage").html(" """+ htmlString +""" ")""")
        return dajax.json()
    else:
        try:
            # is it a valid XML schema ?
            xmlSchema = etree.XMLSchema(xmlTree)
        except Exception, e:
            dajax.script("""
                $("#objectUploadErrorMessage").html("<font color='red'>Not a valid XML schema.</font><br/>"""+e.message.replace("'","") +""" ");
            """)
            return dajax.json()
        
        request.session['uploadObjectValid'] = True
        dajax.script("""
            $("#objectUploadErrorMessage").html("<font color='green'>The uploaded template is valid. You can now save it.</font>   <span class='btn' onclick='saveObject()'>Save</span>");
        """)
        return dajax.json()

    print 'END def uploadObject(request,objectName,objectFilename,objectContent, objectType)'
    return dajax.json()

################################################################################
# 
# Function Name: saveObject(request)
# Inputs:        request - 
# Outputs:       JSON data 
# Exceptions:    None
# Description:   Save an object (template or type) in mongodb
# 
################################################################################
@dajaxice_register
def saveObject(request, buckets):
    print 'BEGIN def saveObject(request)'
    dajax = Dajax()
    
    objectName = None
    objectFilename = None 
    objectContent = None
    objectType = None
    objectFlat = None
    objectApiurl = None
    
    if ('uploadObjectValid' in request.session and request.session['uploadObjectValid'] == True and
        'uploadObjectName' in request.session and request.session['uploadObjectName'] is not None and
        'uploadObjectFilename' in request.session and request.session['uploadObjectFilename'] is not None and
        'uploadObjectContent' in request.session and request.session['uploadObjectContent'] is not None and
        'uploadObjectType' in request.session and request.session['uploadObjectType'] is not None):    
        objectName = request.session['uploadObjectName']
        objectFilename = request.session['uploadObjectFilename'] 
        objectContent = request.session['uploadObjectContent']
        objectType = request.session['uploadObjectType']      
        if 'uploadObjectFlat' in request.session and request.session['uploadObjectFlat'] is not None:
            objectFlat = request.session['uploadObjectFlat']
        else:
            objectFlat = None
        if 'uploadObjectAPIurl' in request.session and request.session['uploadObjectAPIurl'] is not None:
            objectApiurl = request.session['uploadObjectAPIurl']
        else:
            objectApiurl = None  
            
        # save the object
        if objectType == "Template":
            hash = XSDhash.get_hash(objectContent)
            objectVersions = TemplateVersion(nbVersions=1, isDeleted=False).save()            
            object = Template(title=objectName, filename=objectFilename, content=objectContent, version=1, templateVersion=str(objectVersions.id), hash=hash).save()
        elif objectType == "Type":                                                                                    
            objectVersions = TypeVersion(nbVersions=1, isDeleted=False).save()
            object = Type(title=objectName, filename=objectFilename, content=objectContent, version=1, typeVersion=str(objectVersions.id)).save()
            for bucket_id in buckets:
                bucket = Bucket.objects.get(pk=bucket_id)
                bucket.types.append(str(objectVersions.id))
                bucket.save()
        
        objectVersions.versions = [str(object.id)]
        objectVersions.current = str(object.id)
        objectVersions.save()    
        object.save()
        
        if objectFlat is not None and objectApiurl is not None:
            MetaSchema(schemaId=str(object.id), flat_content=objectFlat, api_content=objectApiurl).save()
            
        dajax.script("""
            $( "#dialog-upload-message" ).dialog("close");
            $('#model_selection').load(document.URL +  ' #model_selection', function() {
            loadUploadManagerHandler();
            });
        """)
        clearObject(request)      
    else:
        dajax.script("""$("#objectUploadErrorMessage").html("<font color='red'>Please upload a valid XML schema first.</font>"); """)
        return dajax.json()
    

    print 'END def saveObject(request)'
    return dajax.json()

################################################################################
# 
# Function Name: resolveDependencies(request, dependencies)
# Inputs:        request - 
#                dependencies - 
# Outputs:       JSON data 
# Exceptions:    None
# Description:   Save an object (template or type) in mongodb
# 
################################################################################
@dajaxice_register
def resolveDependencies(request, dependencies):
    print 'BEGIN def resolveDependencies(request, dependencies)'
    dajax = Dajax()
     
    objectContent = None
    
    if ('uploadObjectName' in request.session and request.session['uploadObjectName'] is not None and
        'uploadObjectFilename' in request.session and request.session['uploadObjectFilename'] is not None and
        'uploadObjectContent' in request.session and request.session['uploadObjectContent'] is not None and
        'uploadObjectType' in request.session and request.session['uploadObjectType'] is not None):    
        objectContent = request.session['uploadObjectContent']
#         contentSession = 'uploadObjectContent'
        validSession = 'uploadObjectValid'
        flatSession = 'uploadObjectFlat'
        apiSession = 'uploadObjectAPIurl'
        saveBtn = "<span class='btn' onclick='saveObject()'>Save</span>"
    elif ('uploadVersionFilename' in request.session and request.session['uploadVersionFilename'] is not None and
        'uploadVersionContent' in request.session and request.session['uploadVersionContent'] is not None):
        objectContent = request.session['uploadVersionContent']
#         contentSession = 'uploadVersionContent'
        validSession = 'uploadVersionValid'
        flatSession = 'uploadVersionFlat'
        apiSession = 'uploadVersionAPIurl'
        saveBtn = "<span class='btn' onclick='saveVersion()'>Save</span>"
    else:
        dajax.script("""$("#objectUploadErrorMessage").html("<font color='red'>Please upload a file first.</font><br/>");""")
        return dajax.json()
         
    xmlTree = etree.parse(BytesIO(objectContent.encode('utf-8')))        
    # get the imports
#     imports = xmlTree.findall("{http://www.w3.org/2001/XMLSchema}import")
     
    # get the includes
    includes = xmlTree.findall("{http://www.w3.org/2001/XMLSchema}include")
     
    idxInclude = 0        
    # replace includes/imports by API calls
    for dependency in dependencies:
        includes[idxInclude].attrib['schemaLocation'] = getSchemaLocation(request, str(dependency))
        idxInclude += 1            
     
#         flattener = XSDFlattenerURL(etree.tostring(xmlTree),'admin','admin')
    flattener = XSDFlattenerMDCS(etree.tostring(xmlTree))
    flatStr = flattener.get_flat()
    flatTree = etree.fromstring(flatStr)
    
    try:
        # is it a valid XML schema ?
        xmlSchema = etree.XMLSchema(flatTree)
#         request.session[contentSession] = etree.tostring(xmlTree)
        request.session[validSession] = True
        
        request.session[flatSession] = flatStr
        request.session[apiSession] = etree.tostring(xmlTree)
        dajax.script("""
            $("#objectUploadErrorMessage").html("<font color='green'>The uploaded template is valid. You can now save it.</font>"""+ saveBtn +"""  ");
        """)
    except Exception, e:
        dajax.script("""
            $("#errorDependencies").html("<font color='red'>Not a valid XML schema.</font><br/>"""+e.message.replace("'","") +""" ");
        """)
        return dajax.json()        
    

    print 'END def resolveDependencies(request, dependencies)'
    return dajax.json()


################################################################################
# 
# Function Name: clearObject(request)
# Inputs:        request - 
# Outputs:       JSON data 
# Exceptions:    None
# Description:   Clear variables in the session
# 
################################################################################
@dajaxice_register
def clearObject(request):
    print 'BEGIN def clearObject(request)'
    dajax = Dajax()
    
    if 'uploadObjectName' in request.session:
        del request.session['uploadObjectName']
    if 'uploadObjectFilename' in request.session:
        del request.session['uploadObjectFilename']
    if 'uploadObjectContent' in request.session: 
        del request.session['uploadObjectContent']
    if 'uploadObjectType' in request.session:
        del request.session['uploadObjectType']
    if 'uploadObjectValid' in request.session:
        del request.session['uploadObjectValid']
    if 'uploadObjectFlat' in request.session:
        del request.session['uploadObjectFlat']
    if 'uploadObjectAPIurl' in request.session:
        del request.session['uploadObjectAPIurl']
        
    print 'END def clearObject(request)'
    return dajax.json()


################################################################################
# 
# Function Name: clearVersion(request)
# Inputs:        request - 
# Outputs:       JSON data 
# Exceptions:    None
# Description:   Clear variables in the session
# 
################################################################################
@dajaxice_register
def clearVersion(request):
    print 'BEGIN def clearVersion(request)'
    dajax = Dajax()
    
    if 'uploadVersionValid' in request.session:
        del request.session['uploadVersionValid']
    if 'uploadVersionID' in request.session:
        del request.session['uploadVersionID']
    if 'uploadVersionType' in request.session: 
        del request.session['uploadVersionType']
    if 'uploadVersionFilename' in request.session:
        del request.session['uploadVersionFilename']
    if 'uploadVersionContent' in request.session:
        del request.session['uploadVersionContent']
    if 'uploadVersionFlat' in request.session:
        del request.session['uploadVersionFlat']
    if 'uploadVersionAPIurl' in request.session:
        del request.session['uploadVersionAPIurl']

    print 'END def clearVersion(request)'
    return dajax.json()


################################################################################
# 
# Function Name: generateHtmlDependencyResolver(imports, includes)
# Inputs:        request - 
#                imports -
#                includes - 
# Outputs:       JSON data 
# Exceptions:    None
# Description:   Generate an HTML form to resolve depencies of an uploaded schema
# 
################################################################################
def generateHtmlDependencyResolver(imports, includes):
    #there are includes or imports, need to resolve them            
    htmlString = "Please choose a file from the database to resolve each import/include."
    htmlString += "<table id='dependencies'>"
    htmlString += "<tr><th>Import/Include</th><th>Value</th><th>Dependency</th></tr>"
    
    selectDependencyStr = "<select class='dependency'>"
    for type in Type.objects:
        selectDependencyStr += "<option objectid='"+ str(type.id) +"'>"+ type.title +"</option>"
    selectDependencyStr += "</select>"
    
    for el_include in includes:
        htmlString += "<tr>"
        htmlString += "<td>Include</td>"
        htmlString += "<td><textarea readonly>"+ el_include.attrib['schemaLocation']+"</textarea></td>"
        htmlString += "<td>"+ selectDependencyStr +"</td>"
        htmlString += "</tr>"
        
    htmlString += "</table>"   
    htmlString += "<span class='btn resolve' onclick='resolveDependencies();'>Resolve</span>"
    htmlString += "<div id='errorDependencies'></div>"
    
    return htmlString

################################################################################
# 
# Function Name: deleteObject(request, objectID, objectType)
# Inputs:        request - 
#                objectID - 
#                objectType - 
# Outputs:       JSON data 
# Exceptions:    None
# Description:   Delete an object (template or type).
# 
################################################################################
@dajaxice_register
def deleteObject(request, objectID, objectType):
    print 'BEGIN def deleteXMLSchema(request,xmlSchemaID)'
    dajax = Dajax()

    if objectType == "Template":
        object = Template.objects.get(pk=objectID)
        objectVersions = TemplateVersion.objects.get(pk=object.templateVersion)
    else:
        object = Type.objects.get(pk=objectID)
        objectVersions = TypeVersion.objects.get(pk=object.typeVersion)

    objectVersions.deletedVersions.append(str(object.id))    
    objectVersions.isDeleted = True
    objectVersions.save()

    print 'END def deleteXMLSchema(request,xmlSchemaID)'
    return dajax.json()

################################################################################
# 
# Function Name: setSchemaVersionContent(request, versionContent, versionFilename)
# Inputs:        request - 
#                versionContent -
#                versionFilename - 
# Outputs:       
# Exceptions:    None
# Description:   Save the name and content of uploaded schema before save
#
################################################################################
@dajaxice_register
def setSchemaVersionContent(request, versionContent, versionFilename):
    dajax = Dajax()
    
    request.session['uploadVersionContent'] = versionContent
    request.session['uploadVersionFilename'] = versionFilename 
    request.session['uploadVersionValid'] = False
    
    return dajax.json()

################################################################################
# 
# Function Name: setTypeVersionContent(request, versionContent, versionFilename)
# Inputs:        request - 
#                versionContent -
#                versionFilename - 
# Outputs:       
# Exceptions:    None
# Description:   Save the name and content of uploaded type before save
#
################################################################################
@dajaxice_register
def setTypeVersionContent(request, versionContent, versionFilename):
    dajax = Dajax()
    
    request.session['uploadVersionContent'] = versionContent
    request.session['uploadVersionFilename'] = versionFilename
    request.session['uploadVersionValid'] = False
    
    return dajax.json()

################################################################################
# 
# Function Name: uploadVersion(request, objectVersionID, objectType)
# Inputs:        request - 
#                objectVersionID -
#                objectType - 
# Outputs:       
# Exceptions:    None
# Description:   Upload the object (template or type)
#
################################################################################
@dajaxice_register
def uploadVersion(request, objectVersionID, objectType):
    dajax = Dajax()    
    
    versionContent = None
    
    if ('uploadVersionFilename' in request.session and request.session['uploadVersionFilename'] is not None and
        'uploadVersionContent' in request.session and request.session['uploadVersionContent'] is not None):    
        request.session['uploadVersionID'] = objectVersionID
        request.session['uploadVersionType'] = objectType
        
        versionContent = request.session['uploadVersionContent'] 
       
    
        xmlTree = None
    
        # is it a valid XML document ?
        try:            
            xmlTree = etree.parse(BytesIO(versionContent.encode('utf-8')))
        except Exception, e:
            dajax.script("""$("#objectUploadErrorMessage").html("<font color='red'>Not a valid XML document.</font><br/>"""+e.message.replace("'","") +""" ");""")
            return dajax.json()
        
        # is it supported by the MDCS ?
        errors = utils.getValidityErrorsForMDCS(xmlTree, objectType)
        if len(errors) > 0:
            errorsStr = ""
            for error in errors:
                errorsStr += error + "<br/>"
            dajax.script("""$("#objectUploadErrorMessage").html("<font color='red'>"""+ errorsStr +"""</font>");""")
            return dajax.json() 
        
        # get the imports
        imports = xmlTree.findall("{http://www.w3.org/2001/XMLSchema}import")
        # get the includes
        includes = xmlTree.findall("{http://www.w3.org/2001/XMLSchema}include")
        
        if len(imports) != 0 or len(includes) != 0:
            # Display array to resolve dependencies
            htmlString = generateHtmlDependencyResolver(imports, includes)
            dajax.script("""$("#objectUploadErrorMessage").html(" """+ htmlString +""" ")""")
            return dajax.json()
        else:
            try:
                # is it a valid XML schema ?
                xmlSchema = etree.XMLSchema(xmlTree)
            except Exception, e:
                dajax.script("""
                    $("#objectUploadErrorMessage").html("<font color='red'>Not a valid XML schema.</font><br/>"""+e.message.replace("'","") +""" ");
                """)
                return dajax.json()
            
            request.session['uploadVersionValid'] = True
            dajax.script("""
                $("#objectUploadErrorMessage").html("<font color='green'>The uploaded template is valid. You can now save it.</font>   <span class='btn' onclick='saveVersion()'>Save</span>");
            """)
            return dajax.json()

    print 'END def uploadObject(request,objectName,objectFilename,objectContent, objectType)'
        
    return dajax.json()


################################################################################
# 
# Function Name: saveVersion(request)
# Inputs:        request - 
# Outputs:       JSON data 
# Exceptions:    None
# Description:   Save a version of an object (template or type) in mongodb
# 
################################################################################
@dajaxice_register
def saveVersion(request):
    print 'BEGIN def saveVersion(request, objectType)'
    dajax = Dajax()
    
    versionFilename = None 
    versionContent = None
    objectVersionID = None
    objectType = None
    
    if ('uploadVersionValid' in request.session and request.session['uploadVersionValid'] == True and
        'uploadVersionID' in request.session and request.session['uploadVersionID'] is not None and
        'uploadVersionType' in request.session and request.session['uploadVersionType'] is not None and
        'uploadVersionFilename' in request.session and request.session['uploadVersionFilename'] is not None and
        'uploadVersionContent' in request.session and request.session['uploadVersionContent'] is not None):    
        versionFilename = request.session['uploadVersionFilename']
        versionContent = request.session['uploadVersionContent'] 
        objectVersionID = request.session['uploadVersionID']
        objectType = request.session['uploadVersionType']
        if 'uploadVersionFlat' in request.session and request.session['uploadVersionFlat'] is not None:
            versionFlat = request.session['uploadVersionFlat']
        else:
            versionFlat = None
        if 'uploadVersionAPIurl' in request.session and request.session['uploadVersionAPIurl'] is not None:
            versionApiurl = request.session['uploadVersionAPIurl']
        else:
            versionApiurl = None  
            
        # save the object
        if objectType == "Template":
            objectVersions = TemplateVersion.objects.get(pk=objectVersionID)
            objectVersions.nbVersions += 1
            object = Template.objects.get(pk=objectVersions.current)
            hash = XSDhash.get_hash(versionContent)
            newObject = Template(title=object.title, filename=versionFilename, content=versionContent, version=objectVersions.nbVersions, templateVersion=objectVersionID, hash=hash).save()
        elif objectType == "Type":    
            objectVersions = TypeVersion.objects.get(pk=objectVersionID)
            objectVersions.nbVersions += 1
            object = Type.objects.get(pk=objectVersions.current)                                                                                
            newObject = Type(title=object.title, filename=versionFilename, content=versionContent, version=objectVersions.nbVersions, typeVersion=objectVersionID).save()
        
        objectVersions.versions.append(str(newObject.id))
        objectVersions.save()
        
        if versionFlat is not None and versionApiurl is not None:
            MetaSchema(schemaId=str(newObject.id), flat_content=versionFlat, api_content=versionApiurl).save()
        
        dajax.script("""
            $("#delete_custom_message").html("");
            $('#model_version').load(document.URL +  ' #model_version', function() {}); 
        """)     
        clearVersion(request)
    else:
        dajax.script("""$("#objectUploadErrorMessage").html("<font color='red'>Please upload a valid XML schema first.</font>"); """)
        return dajax.json()
    

    print 'END def saveVersion(request, objectType)'
    return dajax.json()

################################################################################
# 
# Function Name: setCurrentVersion(request, objectid, objectType)
# Inputs:        request - 
#                objectid -
#                objectType - 
# Outputs:       
# Exceptions:    None
# Description:   Set the current version of the object (template or type)
#
################################################################################
@dajaxice_register
def setCurrentVersion(request, objectid, objectType):
    dajax = Dajax()
    
    if objectType == "Template":
        object = Template.objects.get(pk=objectid)
        objectVersions = TemplateVersion.objects.get(pk=object.templateVersion)
    else:
        object = Type.objects.get(pk=objectid)
        objectVersions = TypeVersion.objects.get(pk=object.typeVersion)
    
    objectVersions.current = str(object.id)
    objectVersions.save()
     
    dajax.script("""
        $("#delete_custom_message").html("");   
        $('#model_version').load(document.URL +  ' #model_version', function() {});      
    """)
    
    return dajax.json()

################################################################################
# 
# Function Name: deleteVersion(request, objectid, objectType, newCurrent)
# Inputs:        request - 
#                objectid -
#                objectType - 
#                newCurrent - 
# Outputs:       
# Exceptions:    None
# Description:   Delete a version of the object (template or type) by adding it to the list of deleted
#
################################################################################
@dajaxice_register
def deleteVersion(request, objectid, objectType, newCurrent):
    dajax = Dajax()
    
    if objectType == "Template":
        object = Template.objects.get(pk=objectid)
        objectVersions = TemplateVersion.objects.get(pk=object.templateVersion)
    else:
        object = Type.objects.get(pk=objectid)
        objectVersions = TypeVersion.objects.get(pk=object.typeVersion)
      

    if len(objectVersions.versions) == 1 or len(objectVersions.versions) == len(objectVersions.deletedVersions) + 1:
        objectVersions.deletedVersions.append(str(object.id))    
        objectVersions.isDeleted = True
        objectVersions.save()
        dajax.script("""
            $("#delete_custom_message").html("");
            window.parent.versionDialog.dialog("close");  
        """)
    else:
        if newCurrent != "": 
            objectVersions.current = newCurrent
        objectVersions.deletedVersions.append(str(object.id))   
        objectVersions.save()        
    
        dajax.script("""
            $("#delete_custom_message").html("");   
            $('#model_version').load(document.URL +  ' #model_version', function() {}); 
        """)
    
    return dajax.json()

################################################################################
# 
# Function Name: assignDeleteCustomMessage(request, objectid, objectType)
# Inputs:        request - 
#                objectid -
#                objectType - 
# Outputs:       
# Exceptions:    None
# Description:   Assign a message to the dialog box regarding the situation of the version that is about to be deleted
#
################################################################################
@dajaxice_register
def assignDeleteCustomMessage(request, objectid, objectType):
    dajax = Dajax()
    
    if objectType == "Template":
        object = Template.objects.get(pk=objectid)
        objectVersions = TemplateVersion.objects.get(pk=object.templateVersion)
    else:
        object = Type.objects.get(pk=objectid)
        objectVersions = TypeVersion.objects.get(pk=object.typeVersion)  
    
    message = ""

    if len(objectVersions.versions) == 1:
        message = "<span style='color:red'>You are about to delete the only version of this "+ objectType +". The "+ objectType +" will be deleted from the "+ objectType +" manager.</span>"
    elif objectVersions.current == str(object.id) and len(objectVersions.versions) == len(objectVersions.deletedVersions) + 1:
        message = "<span style='color:red'>You are about to delete the last version of this "+ objectType +". The "+ objectType +" will be deleted from the "+ objectType +" manager.</span>"
    elif objectVersions.current == str(object.id):
        message = "<span>You are about to delete the current version. If you want to continue, please select a new current version: <select id='selectCurrentVersion'>"
        for version in objectVersions.versions:
            if version != objectVersions.current and version not in objectVersions.deletedVersions:
                if objectType == "Template":
                    obj = Template.objects.get(pk=version)
                else:
                    obj = Type.objects.get(pk=version)
                message += "<option value='"+version+"'>Version " + str(obj.version) + "</option>"
        message += "</select></span>"
    
    dajax.script("""
                    $('#delete_custom_message').html(" """+ message +""" ");
                 """)
    
    return dajax.json()

################################################################################
# 
# Function Name: editInformation(request, objectid, objectType, newName, newFilename, buckets)
# Inputs:        request - 
#                objectid -
#                objectType - 
#                newName - 
#                newFileName -
#                buckets - 
# Outputs:       
# Exceptions:    None
# Description:   Edit information of an object (template or type)
#
################################################################################
@dajaxice_register
def editInformation(request, objectid, objectType, newName, newFilename, buckets):
    dajax = Dajax()
    
    if objectType == "Template":
        object = Template.objects.get(pk=objectid)
        objectVersions = TemplateVersion.objects.get(pk=object.templateVersion)
    else:        
        object = Type.objects.get(pk=objectid)
        objectVersions = TypeVersion.objects.get(pk=object.typeVersion)
        # check if a type with the same name already exists
        testFilenameObjects = Type.objects(filename=newFilename)    
        if len(testFilenameObjects) == 1: # 0 is ok, more than 1 can't happen
            #check that the type with the same filename is the current one
            if testFilenameObjects[0].id != object.id:
                dajax.script("""
                    showErrorEditType();
                """)
                return dajax.json()
    
    # change the name of every version but only the filename of the current
    for version in objectVersions.versions:
        if objectType == "Template":
            obj = Template.objects.get(pk=version)
        else:
            obj = Type.objects.get(pk=version)
        obj.title = newName
        if version == objectid:
            obj.filename = newFilename
        obj.save()
        
    # update the buckets
    allBuckets = Bucket.objects
    for bucket in allBuckets:
        if str(bucket.id) in buckets:
            if str(objectVersions.id) not in bucket.types:
                bucket.types.append(str(objectVersions.id))
        
        else:   
            if str(objectVersions.id) in bucket.types:
                bucket.types.remove(str(objectVersions.id))
        
        bucket.save()
    
    
    dajax.script("""
        $("#dialog-edit-info").dialog( "close" );
        $('#model_selection').load(document.URL +  ' #model_selection', function() {
              loadUploadManagerHandler();
        });
    """)
    
    return dajax.json()


################################################################################
# 
# Function Name: restoreObject(request, objectid, objectType)
# Inputs:        request - 
#                objectid -
#                objectType - 
# Outputs:       
# Exceptions:    None
# Description:   Restore an object previously deleted (template or type)
#
################################################################################
@dajaxice_register
def restoreObject(request, objectid, objectType):
    dajax = Dajax()
    
    if objectType == "Template":
        object = Template.objects.get(pk=objectid)
        objectVersions = TemplateVersion.objects.get(pk=object.templateVersion)
    else:
        object = Type.objects.get(pk=objectid)
        objectVersions = TypeVersion.objects.get(pk=object.typeVersion)
        
    objectVersions.isDeleted = False
    del objectVersions.deletedVersions[objectVersions.deletedVersions.index(objectVersions.current)]
    objectVersions.save()
    
    dajax.script("""
        $('#model_selection').load(document.URL +  ' #model_selection', function() {
              loadUploadManagerHandler();
        });
    """)
    
    return dajax.json()

################################################################################
# 
# Function Name: restoreVersion(request, objectid, objectType)
# Inputs:        request - 
#                objectid -
#                objectType - 
# Outputs:       
# Exceptions:    None
# Description:   Restore a version of an object previously deleted (template or type)
#
################################################################################
@dajaxice_register
def restoreVersion(request, objectid, objectType):
    dajax = Dajax()
    
    if objectType == "Template":
        object = Template.objects.get(pk=objectid)
        objectVersions = TemplateVersion.objects.get(pk=object.templateVersion)
    else:
        object = Type.objects.get(pk=objectid)
        objectVersions = TypeVersion.objects.get(pk=object.typeVersion)
        
    del objectVersions.deletedVersions[objectVersions.deletedVersions.index(objectid)]
    objectVersions.save()
       
    dajax.script("""
        $("#delete_custom_message").html("");
        $('#model_version').load(document.URL +  ' #model_version', function() {}); 
    """)
    
    return dajax.json()

################################################################################
# 
# Function Name: addInstance(request, name, protocol, address, port, user, password)
# Inputs:        request - 
#                name -
#                protocol - 
#                address - 
#                port - 
#                user - 
#                password - 
# Outputs:       
# Exceptions:    None
# Description:   Register a remote instance for the federation of queries
#
################################################################################
@dajaxice_register
def addInstance(request, name, protocol, address, port, user, password):
    dajax = Dajax()
    
    errors = ""
    
    # test if the name is "Local"
    if (name == "Local"):
        errors += "By default, the instance named Local is the instance currently running."
    else:
        # test if an instance with the same name exists
        instance = Instance.objects(name=name)
        if len(instance) != 0:
            errors += "An instance with the same name already exists.<br/>"
    
    # test if new instance is not the same as the local instance
    if address == request.META['REMOTE_ADDR'] and port == request.META['SERVER_PORT']:
        errors += "The address and port you entered refer to the instance currently running."
    else:
        # test if an instance with the same address/port exists
        instance = Instance.objects(address=address, port=port)
        if len(instance) != 0:
            errors += "An instance with the address/port already exists.<br/>"
    
    # If some errors display them, otherwise insert the instance
    if(errors == ""):
        status = "Unreachable"
        try:
            url = protocol + "://" + address + ":" + port + "/rest/ping"
            r = requests.get(url, auth=(user, password))
            if r.status_code == 200:
                status = "Reachable"
        except Exception, e:
            pass
        
        Instance(name=name, protocol=protocol, address=address, port=port, user=user, password=password, status=status).save()
        dajax.script("""
        $("#dialog-add-instance").dialog("close");
        $('#model_selection').load(document.URL +  ' #model_selection', function() {
              loadFedOfQueriesHandler();
        });
        """)
    else:
        dajax.assign("#instance_error", "innerHTML", errors)
    
    return dajax.json()

################################################################################
# 
# Function Name: retrieveInstance(request, instanceid)
# Inputs:        request - 
#                instanceid - 
# Outputs:       
# Exceptions:    None
# Description:   Retrieve an instance to edit it
#
################################################################################
@dajaxice_register
def retrieveInstance(request, instanceid):
    dajax = Dajax()
    
    instance = Instance.objects.get(pk=instanceid)
    dajax.script("editInstanceCallback('"+ str(instance.name) +"','"+ str(instance.protocol) +"','"+ str(instance.address) +"','"+ str(instance.port) +"','"+ str(instance.user) +"','"+ str(instance.password) +"','"+ str(instanceid) +"');")
    
    return dajax.json()

################################################################################
# 
# Function Name: editInstance(request, instanceid, name, protocol, address, port, user, password)
# Inputs:        request -
#                instanceid - 
#                name -
#                protocol - 
#                address - 
#                port - 
#                user - 
#                password - 
# Outputs:       
# Exceptions:    None
# Description:   Edit the instance information
#
################################################################################
@dajaxice_register
def editInstance(request, instanceid, name, protocol, address, port, user, password):
    dajax = Dajax()
    
    errors = ""
    
    # test if the name is "Local"
    if (name == "Local"):
        errors += "By default, the instance named Local is the instance currently running."
    else:   
        # test if an instance with the same name exists
        instance = Instance.objects(name=name)
        if len(instance) != 0 and str(instance[0].id) != instanceid:
            errors += "An instance with the same name already exists.<br/>"
    
    # test if new instance is not the same as the local instance
    if address == request.META['REMOTE_ADDR'] and port == request.META['SERVER_PORT']:
        errors += "The address and port you entered refer to the instance currently running."
    else:
        # test if an instance with the same address/port exists
        instance = Instance.objects(address=address, port=port)
        if len(instance) != 0 and str(instance[0].id) != instanceid:
            errors += "An instance with the address/port already exists.<br/>"
    
    # If some errors display them, otherwise insert the instance
    if(errors == ""):
        status = "Unreachable"
        try:
            url = protocol + "://" + address + ":" + port + "/rest/ping"
            r = requests.get(url, auth=(user, password))
            if r.status_code == 200:
                status = "Reachable"
        except Exception, e:
            pass
        
        instance = Instance.objects.get(pk=instanceid)
        instance.name = name
        instance.protocol = protocol
        instance.address = address
        instance.port = port
        instance.user = user
        instance.password = password
        instance.status = status
        instance.save()
        dajax.script("""
        $("#dialog-edit-instance").dialog("close");
        $('#model_selection').load(document.URL +  ' #model_selection', function() {
              loadFedOfQueriesHandler();
        });
        """)
    else:
        dajax.assign("#edit_instance_error", "innerHTML", errors)
    
    return dajax.json()

################################################################################
# 
# Function Name: deleteInstance(request, instanceid)
# Inputs:        request -
#                instanceid -  
# Outputs:       
# Exceptions:    None
# Description:   Delete an instance
#
################################################################################
@dajaxice_register
def deleteInstance(request, instanceid):
    dajax = Dajax()
    
    instance = Instance.objects.get(pk=instanceid)
    instance.delete()
    
    dajax.script("""
        $("#dialog-deleteinstance-message").dialog("close");
        $('#model_selection').load(document.URL +  ' #model_selection', function() {
              loadFedOfQueriesHandler();
        });
    """)
    
    return dajax.json()

################################################################################
# 
# Function Name: requestAccount(request, username, password, firstname, lastname, email)
# Inputs:        request - 
#                username - 
#                password - 
#                firstname - 
#                lastname - 
#                email - 
# Outputs:        
# Exceptions:    None
# Description:   Submit a request for an user account for the system.
# 
################################################################################
@dajaxice_register
def requestAccount(request, username, password, firstname, lastname, email):
    dajax = Dajax()
    try:
        user = User.objects.get(username=username)
        dajax.script("showErrorRequestDialog();")
    except:
        Request(username=username, password=password ,first_name=firstname, last_name=lastname, email=email).save()
        dajax.script("showSentRequestDialog();")
    return dajax.json()

################################################################################
# 
# Function Name: acceptRequest(request, requestid)
# Inputs:        request - 
#                requestid - 
# Outputs:        
# Exceptions:    None
# Description:   Accepts a request and creates the user account
# 
################################################################################
@dajaxice_register
def acceptRequest(request, requestid):
    dajax = Dajax()
    userRequest = Request.objects.get(pk=requestid)
    try:
        existingUser = User.objects.get(username=userRequest.username)
        dajax.script("showErrorRequestDialog();")        
    except:
        user = User.objects.create_user(username=userRequest.username, password=userRequest.password, first_name=userRequest.first_name, last_name=userRequest.last_name, email=userRequest.email)
        user.save()
        userRequest.delete()
        dajax.script("showAcceptedRequestDialog();")
        
    return dajax.json()

################################################################################
# 
# Function Name: denyRequest(request, requestid)
# Inputs:        request - 
#                requestid - 
# Outputs:        
# Exceptions:    None
# Description:   Denies a request
# 
################################################################################
@dajaxice_register
def denyRequest(request, requestid):
    dajax = Dajax()
    userRequest = Request.objects.get(pk=requestid)
    userRequest.delete()
    dajax.script(
    """
      $('#model_selection').load(document.URL +  ' #model_selection', function() {
          loadUserRequestsHandler();
      });
    """)
    return dajax.json()

################################################################################
# 
# Function Name: initModuleManager(request)
# Inputs:        request - 
#                requestid - 
# Outputs:        
# Exceptions:    None
# Description:   Empties the list of resource when come to the module manager
# 
################################################################################
@dajaxice_register
def initModuleManager(request):
    dajax = Dajax()
    
    request.session['listModuleResource'] = []
    
    return dajax.json()

################################################################################
# 
# Function Name: addModuleResource(request, resourceContent, resourceFilename)
# Inputs:        request - 
#                resourceContent - 
#                resourceFilename - 
# Outputs:        
# Exceptions:    None
# Description:   Add a resource for the module. Save the content and name before save.
# 
################################################################################
@dajaxice_register
def addModuleResource(request, resourceContent, resourceFilename):
    dajax = Dajax()
    
    request.session['currentResourceContent'] = resourceContent
    request.session['currentResourceFilename'] = resourceFilename    
    
    return dajax.json()


################################################################################
# 
# Function Name: uploadResource(request)
# Inputs:        request - 
# Outputs:        
# Exceptions:    None
# Description:   Upload the resource
# 
################################################################################
@dajaxice_register
def uploadResource(request):
    dajax = Dajax()
    
    if ('currentResourceContent' in request.session 
        and request.session['currentResourceContent'] != "" 
        and 'currentResourceFilename' in request.session 
        and request.session['currentResourceFilename'] != ""):
            request.session['listModuleResource'].append(ModuleResourceInfo(content=request.session['currentResourceContent'],filename=request.session['currentResourceFilename']).__to_json__())
            dajax.append("#uploadedResources", "innerHTML", request.session['currentResourceFilename'] + "<br/>")
            dajax.script("""$("#moduleResource").val("");""")
            request.session['currentResourceContent'] = ""
            request.session['currentResourceFilename'] = ""
    
    return dajax.json()

################################################################################
# 
# Function Name: addModule(request, template, name, tag, HTMLTag)
# Inputs:        request - 
#                template - 
#                name - 
#                tag - 
#                HTMLTag - 
# Outputs:        
# Exceptions:    None
# Description:   Add a module in mongo db
# 
################################################################################
@dajaxice_register
def addModule(request, templates, name, tag, HTMLTag):
    dajax = Dajax()    
    
    module = Module(name=name, templates=templates, tag=tag, htmlTag=HTMLTag)
    listModuleResource = request.session['listModuleResource']
    for resource in listModuleResource: 
        resource = eval(resource)        
        moduleResource = ModuleResource(name=resource['filename'], content=resource['content'], type=resource['filename'].split(".")[-1])
        module.resources.append(moduleResource)
    
    module.save()

    return dajax.json()

################################################################################
# 
# Function Name: deleteModule(request, objectid)
# Inputs:        request - 
#                objectid - 
# Outputs:        
# Exceptions:    None
# Description:   Delete a module
# 
################################################################################
@dajaxice_register
def deleteModule(request, objectid):
    dajax = Dajax()    
    
    module = Module.objects.get(pk=objectid)
    module.delete()

    return dajax.json()

################################################################################
# 
# Function Name: createBackup(request, mongodbPath)
# Inputs:        request - 
#                mongoPath -  
# Outputs:        
# Exceptions:    None
# Description:   Runs the mongo db command to create a backup of the current mongo instance
# 
################################################################################
@dajaxice_register
def createBackup(request, mongodbPath):
    dajax = Dajax()
    
    backupsDir = settings.SITE_ROOT + '/data/backups/'
    
    now = datetime.now()
    backupFolder = now.strftime("%Y_%m_%d_%H_%M_%S")
    
    backupCommand = mongodbPath + "/mongodump --out " + backupsDir + backupFolder
    retvalue = os.system(backupCommand)
#     result = subprocess.check_output(backupCommand, shell=True)
    if retvalue == 0:
        result = "Backup created with success."
    else:
        result = "Unable to create the backup."
        
    dajax.assign("#backup-message", 'innerHTML', result)
    dajax.script("showBackupDialog();")
    return dajax.json()

################################################################################
# 
# Function Name: restoreBackup(request, mongodbPath, backup)
# Inputs:        request - 
#                mongoPath -  
#                backup - 
# Outputs:        
# Exceptions:    None
# Description:   Runs the mongo db command to restore a backup to the current mongo instance
# 
################################################################################
@dajaxice_register
def restoreBackup(request, mongodbPath, backup):
    dajax = Dajax()
    
    backupsDir = settings.SITE_ROOT + '/data/backups/'
    
    backupCommand = mongodbPath + "/mongorestore " + backupsDir + backup
    retvalue = os.system(backupCommand)
    
    if retvalue == 0:
        result = "Backup restored with success."
    else:
        result = "Unable to restore the backup."
        
    dajax.assign("#backup-message", 'innerHTML', result)
    dajax.script("showBackupDialog();")
    return dajax.json()

################################################################################
# 
# Function Name: restoreBackup(request, backup)
# Inputs:        request -   
#                backup - 
# Outputs:        
# Exceptions:    None
# Description:   Deletes a backup from the list
# 
################################################################################
@dajaxice_register
def deleteBackup(request, backup):
    dajax = Dajax()
    
    backupsDir = settings.SITE_ROOT + '/data/backups/'
    
    for root, dirs, files in os.walk(backupsDir + backup, topdown=False):
        for name in files:
            os.remove(os.path.join(root, name))
        for name in dirs:
            os.rmdir(os.path.join(root, name))
    os.rmdir(backupsDir + backup)
    
    dajax.script(
    """
      $('#model_selection').load(document.URL +  ' #model_selection', function() {});
    """)
    
    return dajax.json()

################################################################################
# 
# Function Name: saveUserProfile(request, userid, username, firstname, lastname, email)
# Inputs:        request -   
#                userid - 
#                username - 
#                firstname -
#                lastname -
#                email - 
# Outputs:        
# Exceptions:    None
# Description:   saves the user profile with the updated information
# 
################################################################################
@dajaxice_register
def saveUserProfile(request, userid, username, firstname, lastname, email):
    dajax = Dajax()
    
    user = User.objects.get(id=userid)
    errors = ""
    if username != user.username:
        try:
            user = User.objects.get(username=username)
            errors += "A user with the same username already exists.<br/>"
            dajax.script("showEditErrorDialog('"+errors+"');")
            return dajax.json()
        except:
            user.username = username
    
    user.first_name = firstname
    user.last_name = lastname
    user.email = email
    user.save()
    dajax.script("showSavedProfileDialog();")
    
    return dajax.json()


################################################################################
# 
# Function Name: changePassword(request, userid, old_password, password)
# Inputs:        request -   
#                userid - 
#                old_password - 
#                password - 
# Outputs:        
# Exceptions:    None
# Description:   Changes the password of the user
# 
################################################################################
@dajaxice_register
def changePassword(request, userid, old_password, password):
    dajax = Dajax()
    
    errors = ""
    user = User.objects.get(id=userid)
    auth_user = authenticate(username=user.username, password=old_password)
    if auth_user is None:
        errors += "The old password is incorrect."
        dajax.script("showChangePasswordErrorDialog('"+ errors +"')")
        return dajax.json()
    else:        
        user.set_password(password)
        user.save()
        dajax.script("showPasswordChangedDialog();")

    
    return dajax.json()

################################################################################
# 
# Function Name: pingRemoteAPI(request, name, protocol, address, port, user, password)
# Inputs:        request -
#                name - 
#                protocol -
#                address - 
#                port -
#                user -
#                password - 
# Outputs:       
# Exceptions:    None
# Description:   Ping a remote instance to see if it is reachable with the given parameters
#
################################################################################
@dajaxice_register
def pingRemoteAPI(request, name, protocol, address, port, user, password):
    dajax = Dajax()
    
    try:
        url = protocol + "://" + address + ":" + port + "/rest/ping"
        r = requests.get(url, auth=(user, password))
        if r.status_code == 200:
            dajax.assign("#instance_error", "innerHTML", "<b style='color:green'>Remote API reached with success.</b>")
        else:
            if 'detail' in eval(r.content):
                dajax.assign("#instance_error", "innerHTML", "<b style='color:red'>Error: " + eval(r.content)['detail'] + "</b>")
            else:
                dajax.assign("#instance_error", "innerHTML", "<b style='color:red'>Error: Unable to reach the remote API.</b>")
    except Exception, e:
        dajax.assign("#instance_error", "innerHTML", "<b style='color:red'>Error: Unable to reach the remote API.</b>")
        
    
    return dajax.json()

################################################################################
# 
# Function Name: contact(request, name, email, message)
# Inputs:        request -
#                name - 
#                email -
#                message - 
# Outputs:       
# Exceptions:    None
# Description:   Send a message to the Administrator
#
################################################################################
@dajaxice_register
def contact(request, name, email, message):
    dajax = Dajax()
    
    Message(name=name, email=email, content=message).save()
    
    return dajax.json()

################################################################################
# 
# Function Name: removeMessage(request, messageid)
# Inputs:        request -
#                messageid - 
# Outputs:       
# Exceptions:    None
# Description:   Remove a message from Contact form
#
################################################################################
@dajaxice_register
def removeMessage(request, messageid):
    dajax = Dajax()
    
    message = Message.objects.get(pk=messageid)
    message.delete()
        
    return dajax.json()

################################################################################
# 
# Function Name: saveTermsOfUse(request, content)
# Inputs:        request -
#                content - 
# Outputs:       
# Exceptions:    None
# Description:   Saves the terms of use
#
################################################################################
@dajaxice_register
def saveTermsOfUse(request, content):
    dajax = Dajax()
    
    for term in TermsOfUse.objects:
        term.delete()
    
    if (content != ""):
        newTerms = TermsOfUse(content = content)
        newTerms.save()
    
    return dajax.json()


################################################################################
# 
# Function Name: savePrivacyPolicy(request, content)
# Inputs:        request -
#                content - 
# Outputs:       
# Exceptions:    None
# Description:   Saves the privacy policy
#
################################################################################
@dajaxice_register
def savePrivacyPolicy(request, content):
    dajax = Dajax()
    
    for privacy in PrivacyPolicy.objects:
        privacy.delete()
    
    if (content != ""):
        newPrivacy = PrivacyPolicy(content = content)
        newPrivacy.save()
    
    return dajax.json()


################################################################################
# 
# Function Name: addBucket(request, label)
# Inputs:        request -
#                label - 
# Outputs:       
# Exceptions:    None
# Description:   Add a new bucket
#
################################################################################
@dajaxice_register
def addBucket(request, label):
    dajax = Dajax()
    
    # check that the label is unique
    labels = Bucket.objects.all().values_list('label') 
    if label in labels:
        dajax.script("""$("#errorAddBucket").html("<font color='red'>A bucket with the same label already exists.</font><br/>");""")
        return dajax.json()
    
    # get an unique color
    colors = Bucket.objects.all().values_list('color') 
    color = rdm_hex_color()
    while color in colors:
        color = rdm_hex_color()
        
    Bucket(label=label, color=color).save()
    dajax.script(
    """
      $('#dialog-add-bucket').dialog('close');
      $('#model_buckets').load(document.URL +  ' #model_buckets', function() {});
      $('#model_select_buckets').load(document.URL +  ' #model_select_buckets', function() {});
      $('#model_select_edit_buckets').load(document.URL +  ' #model_select_edit_buckets', function() {});
    """)
    
    return dajax.json()


################################################################################
# 
# Function Name: addBucket(request, bucket_id)
# Inputs:        request -
#                bucket_id - 
# Outputs:       
# Exceptions:    None
# Description:   Delete a bucket
#
################################################################################
@dajaxice_register
def deleteBucket(request, bucket_id):
    dajax = Dajax()
    
    bucket = Bucket.objects.get(pk=bucket_id)
    bucket.delete()
        
    dajax.script(
    """
      $('#model_buckets').load(document.URL +  ' #model_buckets', function() {});
      $('#model_select_buckets').load(document.URL +  ' #model_select_buckets', function() {});
      $('#model_selection').load(document.URL +  ' #model_selection', function() {
        loadUploadManagerHandler();
      });
      $('#model_select_edit_buckets').load(document.URL +  ' #model_select_edit_buckets', function() {});
    """)
    
    return dajax.json()

################################################################################
# 
# Function Name: rdm_hex_color()
# Inputs:        None
# Outputs:       hex color
# Exceptions:    None
# Description:   Generates a random color code
#
################################################################################
def rdm_hex_color():
    return '#' +''.join([random.choice('0123456789ABCDEF') for x in range(6)])
