import Quickshell
import QtQuick
import QtQuick.Layouts

ShellRoot {
    id: root

    FloatingPanel {
        id: metricsPanel
        
        // Panel properties
        width: 320
        height: 220
        x: 50
        y: 50
        
        // Make it movable
        movable: true
        
        color: "#000000"
        radius: 12
        
        Column {
            anchors {
                fill: parent
                margins: 16
            }
            spacing: 12
            
            // Title Bar
            Text {
                text: "J.A.R.V.I.S. Metrics"
                color: "#00c8ff"
                font.pixelSize: 14
                font.weight: Font.Bold
                width: parent.width
            }
            
            // CPU Monitor
            Rectangle {
                width: parent.width
                height: 30
                color: "transparent"
                
                Row {
                    spacing: 8
                    width: parent.width
                    
                    Text {
                        text: "CPU"
                        color: "#00c8ff"
                        font.pixelSize: 12
                        font.weight: Font.Medium
                        width: 40
                    }
                    
                    Text {
                        text: systemMetrics.cpuUsage.toFixed(1) + "%"
                        color: "#00c8ff"
                        font.pixelSize: 12
                        font.weight: Font.Bold
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }
                
                // Progress bar background
                Rectangle {
                    y: 20
                    color: Qt.rgba(0, 0.784, 1, 0.2)
                    radius: 4
                    height: 8
                    width: parent.width
                    
                    // Progress bar fill with animation
                    Rectangle {
                        color: "#00c8ff"
                        radius: 4
                        height: 8
                        width: (parent.width * (systemMetrics.cpuUsage / 100))
                        
                        Behavior on width {
                            NumberAnimation {
                                duration: 500
                                easing.type: Easing.InOutQuad
                            }
                        }
                    }
                }
            }
            
            // RAM Monitor
            Rectangle {
                width: parent.width
                height: 30
                color: "transparent"
                
                Row {
                    spacing: 8
                    width: parent.width
                    
                    Text {
                        text: "RAM"
                        color: "#00c8ff"
                        font.pixelSize: 12
                        font.weight: Font.Medium
                        width: 40
                    }
                    
                    Text {
                        text: systemMetrics.ramUsage.toFixed(1) + "%"
                        color: "#00c8ff"
                        font.pixelSize: 12
                        font.weight: Font.Bold
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }
                
                // Progress bar background
                Rectangle {
                    y: 20
                    color: Qt.rgba(0, 0.784, 1, 0.2)
                    radius: 4
                    height: 8
                    width: parent.width
                    
                    // Progress bar fill with animation
                    Rectangle {
                        color: "#00c8ff"
                        radius: 4
                        height: 8
                        width: (parent.width * (systemMetrics.ramUsage / 100))
                        
                        Behavior on width {
                            NumberAnimation {
                                duration: 500
                                easing.type: Easing.InOutQuad
                            }
                        }
                    }
                }
            }
            
            // GPU Monitor
            Rectangle {
                width: parent.width
                height: 30
                color: "transparent"
                
                Row {
                    spacing: 8
                    width: parent.width
                    
                    Text {
                        text: "GPU"
                        color: "#00c8ff"
                        font.pixelSize: 12
                        font.weight: Font.Medium
                        width: 40
                    }
                    
                    Text {
                        text: systemMetrics.gpuUsage.toFixed(1) + "%"
                        color: "#00c8ff"
                        font.pixelSize: 12
                        font.weight: Font.Bold
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }
                
                // Progress bar background
                Rectangle {
                    y: 20
                    color: Qt.rgba(0, 0.784, 1, 0.2)
                    radius: 4
                    height: 8
                    width: parent.width
                    
                    // Progress bar fill with animation
                    Rectangle {
                        color: "#00c8ff"
                        radius: 4
                        height: 8
                        width: (parent.width * (systemMetrics.gpuUsage / 100))
                        
                        Behavior on width {
                            NumberAnimation {
                                duration: 500
                                easing.type: Easing.InOutQuad
                            }
                        }
                    }
                }
            }
            
            // Refresh Rate Display
            Text {
                text: "Updated: " + systemMetrics.lastUpdate.toLocaleTimeString()
                color: Qt.rgba(0.627, 0.784, 0.863, 0.75)
                font.pixelSize: 10
                width: parent.width
                horizontalAlignment: Text.AlignRight
            }
        }
    }
    
    // System metrics service
    SystemMetricsService {
        id: systemMetrics
    }
}