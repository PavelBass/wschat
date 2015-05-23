function check_ws(){
    if ('WebSocket' in window){
        return 0
    }else{
        return 1
    }
}

ws = new WebSocket(socket_path);
elem_to_write = document.getElementById('chat');

function send_message(mess){
    mess = 'MESSAGE:' + mess;
    ws.send(mess)
}

function send_command(mess){
    mess = 'COMMAND:' + mess;
}

ws.onmessage = function(evnt){
    var mess = evnt.data;
    var num = mess.indexOf(':');
    var command = mess.substr(0, num);
    mess = mess.substr(num+1);
    if (command=='MESSAGE:'){
        write_message(mess);
    }else if (command=='SERVER:'){
        write_server_message(mess);
    }
};

function write_message(mess){
    var source = elem_to_write.innerHTML;
    elem_to_write.innerHTML = source + '<p>'+mess+'</p>';
}

function write_server_message(mess){
    var source = elem_to_write.innerHTML;
    elem_to_write.innerHTML = source + '<error>'+mess+'</error>';
}

function sender(){
    var elem = document.getElementById('sender');
    var mess = elem.val();
    mess = mess.trim();
    if (mess[0] == '#'){
        send_command(mess);
    }else{
        send_message(mess);
    }
}