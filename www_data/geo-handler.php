<?php
if (preg_match('/^geo:([0-9.-]+),([0-9.-]+)$/', $_GET['l'], $matches))
	header("Location: https://brouter.de/brouter-web/#map=7/50/11/standard&profile=vm-forum-velomobil-schnell&lonlats=$matches[2],$matches[1]");
else
	header("HTTP/1.0 404 Not Found");
?>
