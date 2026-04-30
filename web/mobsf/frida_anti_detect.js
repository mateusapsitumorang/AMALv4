// Hook emulator detection method commonly used by malware
Java.perform(function() {

    // Spoof Build properties (emulator fingerprints)
    var Build = Java.use("android.os.Build");
    Build.MODEL.value = "Pixel 6";
    Build.MANUFACTURER.value = "Google";
    Build.BRAND.value = "google";
    Build.FINGERPRINT.value = "google/oriole/oriole:12/SQ3A.220705.004/8836240:user/release-keys";
    Build.HARDWARE.value = "oriole";
    Build.PRODUCT.value = "oriole";
    Build.DEVICE.value = "oriole";
    Build.TAGS.value = "release-keys";
    Build.TYPE.value = "user";

    // Hook TelephonyManager (check IMEI, operator, etc.)
    var TelephonyManager = Java.use("android.telephony.TelephonyManager");
    TelephonyManager.getDeviceId.overload().implementation = function() {
        return "358240051111110"; // IMEI 
    };
    TelephonyManager.getNetworkOperatorName.implementation = function() {
        return "T-Mobile";
    };
    TelephonyManager.getSimOperatorName.implementation = function() {
        return "T-Mobile";
    };
    TelephonyManager.getPhoneType.implementation = function() {
        return 1; // PHONE_TYPE_GSM
    };
    TelephonyManager.getNetworkType.implementation = function() {
        return 13; // NETWORK_TYPE_LTE
    };

    // Hook file-based emulator checks (/proc/cpuinfo, qemu traces)
    var File = Java.use("java.io.File");
    var suspiciousPaths = [
        "/dev/socket/qemud",
        "/dev/qemu_pipe",
        "/system/lib/libc_malloc_debug_qemu.so",
        "/sys/qemu_trace",
        "/system/bin/qemu-props",
    ];
    File.exists.implementation = function() {
        var path = this.getAbsolutePath();
        for (var i = 0; i < suspiciousPaths.length; i++) {
            if (path === suspiciousPaths[i]) {
                console.log("[AntiDetect] Blocked emulator file check: " + path);
                return false;
            }
        }
        return this.exists();
    };

    // Hook System.getProperty for qemu/goldfish
    var System = Java.use("java.lang.System");
    System.getProperty.overload("java.lang.String").implementation = function(key) {
        if (key === "ro.hardware" || key === "ro.kernel.qemu") {
            return null;
        }
        return this.getProperty(key);
    };

    // Hook sensor checks 
    var SensorManager = Java.use("android.hardware.SensorManager");
    SensorManager.getDefaultSensor.overload("int").implementation = function(type) {
        var sensor = this.getDefaultSensor(type);
        // Return dummy if null
        return sensor;
    };

    console.log("[AntiDetect] Anti-emulator hooks loaded successfully");
});