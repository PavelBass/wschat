function check_ws(){
    if ('WebSocket' in window){
        return 0
    }else{
        return 1
    }
}

var ws = new WebSocket(socket_path);
elem_to_write = document.getElementById('chat');

ws.onmessage = function(evnt){
    console.log(evnt.data)
    var mess = evnt.data;
    var num = mess.indexOf(':');
    var command = mess.substr(0, num);
    mess = mess.substr(num+1);
    if (command=='MESSAGE'){
        write_message(mess);
    }else if (command=='SERVER'){
        write_server_message(mess);
    }
};

ws.onclose = function(){
    var source = elem_to_write.innerHTML;
    source  = source + '<br><p>&nbsp;</p><error>You was disconnected.' +
    '<br>Refresh page to create new connection.</error>';
    elem_to_write.innerHTML = source;
}

function write_message(mess){
    var source = elem_to_write.innerHTML;
    elem_to_write.innerHTML = source + '<p>'+mess+'</p>';
}

function write_server_message(mess){
    var source = elem_to_write.innerHTML;
    elem_to_write.innerHTML = source + '<server>'+mess+'</server>';
}

function sender_click(){
    var elem = document.getElementById('sendmessage');
    var mess = elem.value;
    ws.send(mess);
    elem.value = '';
}

function sender_enter_key(event){
    if(event.which == 13 || event.keyCode == 13) {
        sender_click()
    }
}


document.getElementById('sender_button').onclick = sender_click;
document.getElementById('sendmessage').onkeyup = sender_enter_key;
