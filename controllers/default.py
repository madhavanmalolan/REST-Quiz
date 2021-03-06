# -*- coding: utf-8 -*-
# this file is released under public domain and you can use without limitations

#########################################################################
## This is a samples controller
## - index is the default action of any application
## - user is required for authentication and authorization
## - download is for downloading files uploaded in the db (does streaming)
## - call exposes all registered services (none by default)
#########################################################################
import cStringIO
import pycurl
import shutil
import string
import random
import os
import urllib
import json
def index():
    """
    example action using the internationalization operator T and flash
    rendered by views/default/index.html or views/generic.html
    """
    response.flash = "Welcome to Felicity!"
    events = db(db.events.id>0).select()
    title = T('Threads at Felicity-2013')
    about = T('Threads is the annual online programming and quizzing event at Felicity. This sees great amount of participation from over  67 countries')
    return dict(events = events,about = about,title=title)
def event_home():
    tab_id = int(request.get_vars['tab_id'])
    event_id = int(request.get_vars['event_id'])
    row = db((db.event_tab.id>0 )& (db.event_tab.event_id==event_id) & (db.event_tab.tab_id==tab_id)).select()

    about = "Felicity is IIIT-Hyderabad's annual technno-cultural Festival."
    title = "Error!"

    if(row):
        about = row[0].raw_content
        title = row[0].title
    tabs = db((db.event_tab.id>0) & (db.event_tab.event_id==event_id)).select()
    return dict(about = about,title=title,tabs = tabs,event_id = event_id)


@auth.requires_login()
def questions():
    event_id = int(request.get_vars['event_id'])
    question_no = int(request.get_vars['question_no'])
    if 'message' in request.get_vars.keys():
        response.flash = request.get_vars['message']

    event_details= db(db.events.id==event_id).select()[0]
    #If User is NOT registered for the given event , register him/her with default score = 0
    user_id = auth.user.id 
    event_user_rows = db((db.event_user.event_id==event_id)&(db.event_user.user_id == user_id)).select()
    if len(event_user_rows) <= 0:
        response.flash = "Woa a new competitor!"
        db.event_user.insert(event_id=event_id,user_id = user_id,score=0,status='Participating',penalty=0,current_question=1)  
    elif( int(event_details.flow_of_questions) == 1 ):
        question_no= event_user_rows[0].current_question


    #Tabs to be displayed on the RHS block
    tabs = db((db.event_tab.id>0) & (db.event_tab.event_id==event_id)).select()
    


    #Comments Form
    db.comments.user_id.default = user_id
    db.comments.event_id.default = event_id
    db.comments.question_no.default = question_no
    form = SQLFORM(db.comments)
    if form.process().accepted:
        response.flash = "Comment will become public after moderation"

    if(question_no > 0):
        all_comments = db((db.comments.event_id==event_id)&(db.comments.question_no==question_no)).select()
    else:
        all_comments = []

    
    a = int(event_details.flow_of_questions)
    response.flash = a
    if(question_no == 0 and a == 2):
        list_of_questions = db((db.question.id>0)&(db.question.event== event_id)).select()
        question_title = "List of questions"
        return dict(user_details = auth.user,question_title = question_title, list_of_questions=list_of_questions,tabs = tabs, event_id = event_id,form=form,comments=all_comments)
    
    else:
        question_details = db((db.question.event ==event_id) & (db.question.question_no == question_no)).select()[0]
        if(question_details):
            question_title = question_details.title
    
            return dict(user_details = auth.user,question_title= question_title,question_statement = question_details.question, answer = question_details.answer,tabs=tabs,event_id=event_id,user_id = user_id,question_no = question_no,form=form,comments=all_comments)


@auth.requires_login()
def judge():
    question_no = int(request.get_vars['question_no'])
    event_id = int(request.get_vars['event_id'])

    user_id = auth.user.id
    user_event = db((db.event_user.user_id == user_id)&(db.event_user.event_id==event_id)).select()[0]
    question_no = int(user_event['current_question'])
    #Dictionary that will hold all the data to be passed to the black-box judge
    post_vars = {}
    file_size = 0
    for key in request.vars.keys():
        post_vars[key] = request.vars[key]
    #If thtere is a file upload. NOTE that any question may have a MAXIMUM of one file upload per question.
    if 'file' in request.vars.keys():
        # THis will take the file, write it on to the file and transfer it to the judge's local system.
        # uses POST for input and SCP for transfering. Make sure that the judge's authorized_keys has the Apache's key in it. Basically a passwordless login should be enabled for user 'apache'
        filename = request.vars.file.filename
        file_descriptor = request.vars.file.file
        file_descriptor.seek(0,2)
        file_size = file_descriptor.tell()
        file_descriptor.seek(0,0)   
        temp_dir = "/tmp/Felicity/"

        # Temp filename = submission_<EVENT-ID>_<USER-ID>_<Unique-string>.<ext>
        temp_storage_file = "submission_"+str(question_no)+"_"+str(event_id)+"_"+str(auth.user.id)+str(''.join(random.choice(string.ascii_uppercase + string.digits) for x in range(5)))+os.path.splitext(filename)[1]
        temp_storage_filename = temp_dir + temp_storage_file
        shutil.copyfileobj(file_descriptor,open(temp_storage_filename,'wb'))
         
        row = db(db.events.id==event_id).select()[0]
        #Transfer the string using SCP.
        organizer = row['organizer']
        judge_ip = row['judge'].split(':')[0]
        scp= 'scp %s felicity@localhost:~/judge/uploads/.'%(temp_storage_filename)#,organizer,judge_ip)
        os.system(scp)
        post_vars['file'] = scp
        
        



    #Convert the variables to be passed into a form passable thru GET
    data_post = urllib.urlencode(post_vars)

    #Establish a connection, and communicate with the blackbox judge using cURL
    #Based on what is sent to the black-box judge, it will reply with the following :
    #    1. Event-ID
    #    2. Score increment
    #    3. Penalty increment
    #    4. Current question in case of an event with sequential questions.
    #    5. Status to be displayed : ususally "correct", "wrong" or the like
    buf = cStringIO.StringIO()
    c = pycurl.Curl()
    curl_request = "http://localhost:10001"
    c.setopt(pycurl.URL, curl_request)
    c.setopt(pycurl.POST,1)
    c.setopt(pycurl.POSTFIELDS, data_post)
    c.setopt(pycurl.WRITEFUNCTION, buf.write)
    c.perform()
    ret_val = buf.getvalue()
    buf.close()
    #End of communication

   
    
    response_dict = json.loads(ret_val) #converts the response string into a dictionary understandable by Python


    
    #Update the user with the response obtained above. 
    db((db.event_user.event_id == response_dict['event_id'])&(db.event_user.user_id == user_id)).update(score = int(user_event['score'])+response_dict['score'], status = response_dict['status'],penalty=int(response_dict['penalty'])+int(user_event['penalty']),current_question = int(response_dict['current_question']))
    response.flash = (response_dict['status'])

    #Re-direct Back to the Questions page. Either : list of questions for nonseq. type and current question for seq. type event.
    redirect('questions?question_no=0&event_id='+str(event_id)+"&message="+response_dict['status']) 
    return dict(text=ret_val)



def scoreboard():
    event_id = request.get_vars['event_id']
    scorers = db(db.event_user.event_id == event_id).select(orderby=db.event_user.score)
    tabs = db((db.event_tab.id>0) & (db.event_tab.event_id==event_id)).select()
    return dict(scoreboard = scorers, tabs = tabs, event_id= event_id)



def user():
    """
    exposes:
    http://..../[app]/default/user/login
    http://..../[app]/default/user/logout
    http://..../[app]/default/user/register
    http://..../[app]/default/user/profile
    http://..../[app]/default/user/retrieve_password
    http://..../[app]/default/user/change_password
    use @auth.requires_login()
        @auth.requires_membership('group name')
        @auth.requires_permission('read','table name',record_id)
    to decorate functions that need access control
    """
    return dict(form=auth())


def download():
    """
    allows downloading of uploaded files
    http://..../[app]/default/download/[filename]
    """
    return response.download(request,db)


def call():
    """
    exposes services. for example:
    http://..../[app]/default/call/jsonrpc
    decorate with @services.jsonrpc the functions to expose
    supports xml, json, xmlrpc, jsonrpc, amfrpc, rss, csv
    """
    return service()


@auth.requires_signature()
def data():
    """
    http://..../[app]/default/data/tables
    http://..../[app]/default/data/create/[table]
    http://..../[app]/default/data/read/[table]/[id]
    http://..../[app]/default/data/update/[table]/[id]
    http://..../[app]/default/data/delete/[table]/[id]
    http://..../[app]/default/data/select/[table]
    http://..../[app]/default/data/search/[table]
    but URLs must be signed, i.e. linked with
      A('table',_href=URL('data/tables',user_signature=True))
    or with the signed load operator
      LOAD('default','data.load',args='tables',ajax=True,user_signature=True)
    """
    return dict(form=crud())

